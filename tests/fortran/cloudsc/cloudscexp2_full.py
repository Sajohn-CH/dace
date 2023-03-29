# Copyright 2019-2023 ETH Zurich and the DaCe authors. All rights reserved.
import copy
import dace
from dace.frontend.fortran import fortran_parser
from dace.sdfg import utils
from dace.transformation.auto.auto_optimize import auto_optimize, greedy_fuse, tile_wcrs
from dace.transformation.pass_pipeline import Pipeline
from dace.transformation.passes import RemoveUnusedSymbols, ScalarToSymbolPromotion, ScalarFission
from importlib import import_module
import numpy as np
from numbers import Integral, Number
from numpy import f2py
import os
import pytest
import sys
import tempfile
from typing import Dict, Union

# Transformations
from dace.transformation.dataflow import MapCollapse, TrivialMapElimination, MapFusion, ReduceExpansion
from dace.transformation.interstate import LoopToMap, RefineNestedAccess
from dace.transformation.subgraph.composite import CompositeFusion
from dace.transformation.subgraph import helpers as xfsh
from dace.transformation import helpers as xfh


def read_source(filename: str, extension: str = 'f90') -> str:
    source = None
    with open(os.path.join(os.path.dirname(__file__), f'{filename}.{extension}'), 'r') as file:
        source = file.read()
    assert source
    return source


def get_fortran(source: str, program_name: str, subroutine_name: str, fortran_extension: str = '.f90'):
    with tempfile.TemporaryDirectory() as tmp_dir:
        cwd = os.getcwd()
        os.chdir(tmp_dir)
        f2py.compile(source, modulename=program_name, extra_args=["--opt='-fdefault-real-8'"], verbose=True, extension=fortran_extension)
        sys.path.append(tmp_dir)
        module = import_module(program_name)
        function = getattr(module, subroutine_name.lower())
        os.chdir(cwd)
        return function


def get_sdfg(source: str, program_name: str, normalize_offsets: bool = False) -> dace.SDFG:

    source_fixed=source.replace("_JPRB","")
    intial_sdfg = fortran_parser.create_sdfg_from_string(source_fixed, program_name)
    
    # Find first NestedSDFG
    sdfg = None
    for state in intial_sdfg.states():
        for node in state.nodes():
            if isinstance(node, dace.nodes.NestedSDFG):
                sdfg = node.sdfg
                break
    if not sdfg:
        raise ValueError("SDFG not found.")

    sdfg.parent = None
    sdfg.parent_sdfg = None
    sdfg.parent_nsdfg_node = None
    sdfg.reset_sdfg_list()

    # if normalize_offsets:
    #     my_simplify = Pipeline([RemoveUnusedSymbols(), ScalarToSymbolPromotion()])
    # else:
    #     my_simplify = Pipeline([RemoveUnusedSymbols()])
    # my_simplify.apply_pass(sdfg, {})

    # if normalize_offsets:
    #     utils.normalize_offsets(sdfg)
    
    for sd in sdfg.all_sdfgs_recursive():
        promoted = ScalarToSymbolPromotion().apply_pass(sd, {})
        print(f"Promoted the following scalars: {promoted}")
    from dace.sdfg import utils
    utils.normalize_offsets(sdfg)
    sdfg.simplify(verbose=True)
    pipeline = Pipeline([ScalarFission()])
    for sd in sdfg.all_sdfgs_recursive():
        results = pipeline.apply_pass(sd, {})[ScalarFission.__name__]

    return sdfg


def validate_sdfg(sdfg, inputs, outputs, outputs_f) -> bool:
    outputs_d = copy.deepcopy(outputs)
    sdfg(**inputs, **outputs_d)

    success = True
    for k in outputs_f.keys():
        farr = outputs_f[k]
        darr = outputs_d[k]
        if np.allclose(farr, darr):
            print(f"{k}: OK!")
        else:
            print(f"{k}: relative error is {np.linalg.norm(farr - darr) / np.linalg.norm(farr)}")
            success = False
    
    return success
        # assert np.allclose(farr, darr)


def debug_auto_optimize(sdfg: dace.SDFG, inputs, outputs, ref_outputs):

    device = dace.DeviceType.Generic
    validate = False
    validate_all = False

    sdfg.save(f"{sdfg.name}_autoopt_0.sdfg")
    if not validate_sdfg(sdfg, inputs, outputs, ref_outputs):
        return


    # Simplification and loop parallelization
    transformed = True
    sdfg.apply_transformations_repeated(TrivialMapElimination, validate=validate, validate_all=validate_all)

    sdfg.save(f"{sdfg.name}_autoopt_1.sdfg")
    if not validate_sdfg(sdfg, inputs, outputs, ref_outputs):
        return

    i = 2
    while transformed:
        sdfg.simplify(validate=False, validate_all=validate_all)

        sdfg.save(f"{sdfg.name}_autoopt_{i}.sdfg")
        i += 1
        if not validate_sdfg(sdfg, inputs, outputs, ref_outputs):
            return

        for s in sdfg.sdfg_list:
            xfh.split_interstate_edges(s)
        l2ms = sdfg.apply_transformations_repeated((LoopToMap, RefineNestedAccess),
                                                   validate=False,
                                                   validate_all=validate_all,
                                                   func=validate_sdfg, args=[inputs, outputs, ref_outputs])
        transformed = l2ms > 0

        sdfg.save(f"{sdfg.name}_autoopt_{i}.sdfg")
        i += 1
        if not validate_sdfg(sdfg, inputs, outputs, ref_outputs):
            return

    # Collapse maps and eliminate trivial dimensions
    sdfg.simplify()

    sdfg.save(f"{sdfg.name}_autoopt_{i}.sdfg")
    i += 1
    if not validate_sdfg(sdfg, inputs, outputs, ref_outputs):
        return

    sdfg.apply_transformations_repeated(MapCollapse, validate=False, validate_all=validate_all)
    sdfg.save(f"{sdfg.name}_autoopt_{i}.sdfg")
    i += 1
    if not validate_sdfg(sdfg, inputs, outputs, ref_outputs):
        return

    # fuse subgraphs greedily
    sdfg.simplify()

    sdfg.save(f"{sdfg.name}_autoopt_{i}.sdfg")
    i += 1
    if not validate_sdfg(sdfg, inputs, outputs, ref_outputs):
        return

    greedy_fuse(sdfg, device=device, validate_all=validate_all)

    sdfg.save(f"{sdfg.name}_autoopt_{i}.sdfg")
    i += 1
    if not validate_sdfg(sdfg, inputs, outputs, ref_outputs):
        return

    # fuse stencils greedily
    greedy_fuse(sdfg, device=device, validate_all=validate_all, recursive=False, stencil=True)

    sdfg.save(f"{sdfg.name}_autoopt_{i}.sdfg")
    i += 1
    if not validate_sdfg(sdfg, inputs, outputs, ref_outputs):
        return

    # Move Loops inside Maps when possible
    from dace.transformation.interstate import MoveLoopIntoMap
    # sdfg.apply_transformations_repeated([MoveLoopIntoMap])

    # # Apply GPU transformations and set library node implementations
    # if device == dtypes.DeviceType.GPU:
    #     sdfg.apply_gpu_transformations()
    #     sdfg.simplify()

    # if device == dtypes.DeviceType.FPGA:
    #     # apply FPGA Transformations
    #     sdfg.apply_fpga_transformations()
    #     fpga_auto_opt.fpga_global_to_local(sdfg)
    #     fpga_auto_opt.fpga_rr_interleave_containers_to_banks(sdfg)

    #     # Set all library nodes to expand to fast library calls
    #     set_fast_implementations(sdfg, device)
    #     return sdfg

    # Tiled WCR and streams
    for nsdfg in list(sdfg.all_sdfgs_recursive()):
        tile_wcrs(nsdfg, validate_all)
    
    sdfg.save(f"{sdfg.name}_autoopt_{i}.sdfg")
    i += 1
    if not validate_sdfg(sdfg, inputs, outputs, ref_outputs):
        return

    # Collapse maps
    sdfg.apply_transformations_repeated(MapCollapse, validate=False, validate_all=validate_all)
    for node, _ in sdfg.all_nodes_recursive():
        # Set OMP collapse property to map length
        if isinstance(node, dace.sdfg.nodes.MapEntry):
            # FORNOW: Leave out
            # node.map.collapse = len(node.map.range)
            pass
    
    sdfg.save(f"{sdfg.name}_autoopt_{i}.sdfg")
    i += 1
    if not validate_sdfg(sdfg, inputs, outputs, ref_outputs):
        return

    # if device == dtypes.DeviceType.Generic:
    #     # Validate at the end
    #     if validate or validate_all:
    #         sdfg.validate()

    #     return sdfg
    return sdfg


parameters = {
    'KLON': 4,
    # 'KLON': 128,
    'KLEV': 137,
    'KIDIA': 1,
    'KFDIA': 4,
    # 'KFDIA': 128,
    'KFLDX': 25,

    'NCLV': 5,
    'NCLDQI': 2,
    'NCLDQL': 1,
    'NCLDQR': 3,
    'NCLDQS': 4,
    'NCLDQV': 5,
    'NCLDTOP': 1,
    'NSSOPT': 1,
    'NAECLBC': 1,
    'NAECLDU': 1,
    'NAECLOM': 1,
    'NAECLSS': 1,
    'NAECLSU': 1,
    'NCLDDIAG': 1,
    'NAERCLD': 1,

    'NBLOCKS': 1,
    # 'NBLOCKS': 512,
    # 'LDMAINCALL': np.bool_(True),  # boolean (LOGICAL)
    # 'LDSLPHY': np.bool_(True),  # boolean (LOGICAL),
    # 'LAERLIQAUTOCP': np.bool_(True),  # boolean (LOGICAL)
    # 'LAERLIQAUTOCPB': np.bool_(True),  # boolean (LOGICAL)
    # 'LAERLIQAUTOLSP': np.bool_(True),  # boolean (LOGICAL)
    # 'LAERLIQCOLL': np.bool_(True),  # boolean (LOGICAL)
    # 'LAERICESED': np.bool_(True),  # boolean (LOGICAL)
    # 'LAERICEAUTO': np.bool_(True),  # boolean (LOGICAL)
    # 'LCLDEXTRA': np.bool_(True),  # boolean (LOGICAL)
    # 'LCLDBUDGET': np.bool_(True),  # boolean (LOGICAL)
    'LDMAINCALL': np.int32(np.bool_(True)),  # boolean (LOGICAL)
    'LDSLPHY': np.int32(np.bool_(True)),  # boolean (LOGICAL),
    'LAERLIQAUTOCP': np.int32(np.bool_(True)),  # boolean (LOGICAL)
    'LAERLIQAUTOCPB': np.int32(np.bool_(True)),  # boolean (LOGICAL)
    'LAERLIQAUTOLSP': np.int32(np.bool_(True)),  # boolean (LOGICAL)
    'LAERLIQCOLL': np.int32(np.bool_(True)),  # boolean (LOGICAL)
    'LAERICESED': np.int32(np.bool_(True)),  # boolean (LOGICAL)
    'LAERICEAUTO': np.int32(np.bool_(True)),  # boolean (LOGICAL)
    'LCLDEXTRA': np.int32(np.bool_(True)),  # boolean (LOGICAL)
    'LCLDBUDGET': np.int32(np.bool_(True)),  # boolean (LOGICAL)
    'NGPBLKS': 10,
    'NUMOMP': 10,
    'NGPTOT': 4*1,
    # 'NGPTOT': 65536,
    'NGPTOTG': 4*1,
    'NGPTOTG': 65536,
    'NPROMA': 4,
    # 'NPROMA': 128,
    'NBETA': 1,
}


data = {
    'NSHAPEP': (0,),
    'NSHAPEQ': (0,),
    'PTSPHY': (0,),
    'R2ES': (0,),
    'R3IES': (0,),
    'R3LES': (0,),
    'R4IES': (0,),
    'R4LES': (0,),
    'R5ALSCP': (0,),
    'R5ALVCP': (0,),
    'R5IES': (0,),
    'R5LES': (0,),
    'RALFDCP': (0,),
    'RALSDCP': (0,),
    'RALVDCP': (0,),
    'RAMID': (0,),
    'RAMIN': (0,),
    'RBETA': (0,),
    'RBETAP1': (0,),
    'RCCN': (0,),
    'RCCNOM': (0,),
    'RCCNSS': (0,),
    'RCCNSU': (0,),
    'RCL_AI': (0,),
    'RCL_BI': (0,),
    'RCL_CI': (0,),
    'RCL_DI': (0,),
    'RCL_X1I': (0,),
    'RCLCRIT': (0,),
    'RCLCRIT_LAND': (0,),
    'RCLCRIT_SEA': (0,),
    'RCLDIFF': (0,),
    'RCLDIFF_CONVI': (0,),
    'RCLDMAX': (0,),
    'RCLDTOPCF': (0,),
    'RCLDTOPP': (0,),
    'RCOVPMIN': (0,),
    'RCPD': (0,),
    'RD': (0,),
    'RDEPLIQREFDEPTH': (0,),
    'RDEPLIQREFRATE': (0,),
    'RETV': (0,),
    'RG': (0,),
    'RICEHI1': (0,),
    'RICEHI2': (0,),
    'RICEINIT': (0,),
    'RKCONV': (0,),
    'RKOOP1': (0,),
    'RKOOP2': (0,),
    'RKOOPTAU': (0,),
    'RLCRITSNOW': (0,),
    'RLMIN': (0,),
    'RLMLT': (0,),
    'RLSTT': (0,),
    'RLVTT': (0,),
    'RNICE': (0,),
    'RPECONS': (0,),
    'RPRC1': (0,),
    'RPRC2': (0,),
    'RPRECRHMAX': (0,),
    'RSNOWLIN1': (0,),
    'RSNOWLIN2': (0,),
    'RTAUMEL': (0,),
    'RTHOMO': (0,),
    'RTICE': (0,),
    'RTICECU': (0,),
    'RTT': (0,),
    'RTWAT': (0,),
    'RTWAT_RTICE_R': (0,),
    'RTWAT_RTICECU_R': (0,),
    'RV': (0,),
    'RVICE': (0,),
    'RVRAIN': (0,),
    'RVRFACTOR': (0,),
    'RVSNOW': (0,),
    'ZEPSEC': (0,),
    'ZEPSILON': (0,),
    'ZRG_R': (0,),
    'ZRLDCP': (0,),
    'ZQTMST': (0,),
    'ZVPICE': (0,),
    'ZVPLIQ': (0,),
    'RCL_KKAac': (0,),
    'RCL_KKBac': (0,),
    'RCL_KKAau': (0,),
    'RCL_KKBauq': (0,),
    'RCL_KKBaun': (0,),
    'RCL_KK_CLOUD_NUM_SEA': (0,),
    'RCL_KK_CLOUD_NUM_LAND': (0,),
    'RCL_CONST1I': (0,),
    'RCL_CONST2I': (0,),
    'RCL_CONST3I': (0,),
    'RCL_CONST4I': (0,),
    'RCL_CONST5I': (0,),
    'RCL_CONST6I': (0,),
    'RCL_APB1': (0,),
    'RCL_APB2': (0,),
    'RCL_APB3': (0,),
    'RCL_CONST1S': (0,),
    'RCL_CONST2S': (0,),
    'RCL_CONST3S': (0,),
    'RCL_CONST4S': (0,),
    'RCL_CONST5S': (0,),
    'RCL_CONST6S': (0,),
    'RCL_CONST7S': (0,),
    'RCL_CONST8S': (0,),
    'RDENSREF': (0,),
    'RCL_KA273': (0,),
    'RCL_CDENOM1': (0,),
    'RCL_CDENOM2': (0,),
    'RCL_CDENOM3': (0,),
    'RCL_CONST1R': (0,),
    'RCL_CONST2R': (0,),
    'RCL_CONST3R': (0,),
    'RCL_CONST4R': (0,),
    'RCL_FAC1': (0,),
    'RCL_FAC2': (0,),
    'RCL_CONST5R': (0,),
    'RCL_CONST6R': (0,),
    'RCL_FZRAB': (0,),
    'RCL_X2I': (0,),
    'RCL_X3I': (0,),
    'RCL_X4I': (0,),
    'RCL_AS': (0,),
    'RCL_BS': (0,),
    'RCL_CS': (0,),
    'RCL_DS': (0,),
    'RCL_X1S': (0,),
    'RCL_X2S': (0,),
    'RCL_X3S': (0,),
    'RCL_X4S': (0,),
    'RDENSWAT': (0,),
    'RCL_AR': (0,),
    'RCL_BR': (0,),
    'RCL_CR': (0,),
    'RCL_DR': (0,),
    'RCL_X1R': (0,),
    'RCL_X2R': (0,),
    'RCL_X4R': (0,),
    'RCL_SCHMIDT': (0,),
    'RCL_DYNVISC': (0,),
    'RCL_FZRBB': (0,),
    'IPHASE': (parameters['NCLV'],),
    'KTYPE': [(parameters['KLON'], parameters['NBLOCKS']), np.int32],
    'LDCUM': [(parameters['KLON'], parameters['NBLOCKS']), np.bool_],
    'PA': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'PAP': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'PAPH': (parameters['KLON'], parameters['KLEV']+1, parameters['NBLOCKS']),
    'PCCN': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'PCLV': (parameters['KLON'], parameters['KLEV'], parameters['NCLV'], parameters['NBLOCKS']),
    'PCOVPTOT': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'PDYNA': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'PDYNI': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'PDYNL': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'PEXTRA': (parameters['KLON'], parameters['KLEV'], parameters['KFLDX'], parameters['NBLOCKS']),
    'PFCQLNG': (parameters['KLON'], parameters['KLEV']+1, parameters['NBLOCKS']),
    'PFCQNNG': (parameters['KLON'], parameters['KLEV']+1, parameters['NBLOCKS']),
    'PFCQRNG': (parameters['KLON'], parameters['KLEV']+1, parameters['NBLOCKS']),
    'PFCQSNG': (parameters['KLON'], parameters['KLEV']+1, parameters['NBLOCKS']),
    'PFHPSL': (parameters['KLON'], parameters['KLEV']+1, parameters['NBLOCKS']),
    'PFHPSN': (parameters['KLON'], parameters['KLEV']+1, parameters['NBLOCKS']),
    'PFPLSL': (parameters['KLON'], parameters['KLEV']+1, parameters['NBLOCKS']),
    'PFPLSN': (parameters['KLON'], parameters['KLEV']+1, parameters['NBLOCKS']),
    'PFSQIF': (parameters['KLON'], parameters['KLEV']+1, parameters['NBLOCKS']),
    'PFSQITUR': (parameters['KLON'], parameters['KLEV']+1, parameters['NBLOCKS']),
    'PFSQLF': (parameters['KLON'], parameters['KLEV']+1, parameters['NBLOCKS']),
    'PFSQLTUR': (parameters['KLON'], parameters['KLEV']+1, parameters['NBLOCKS']),
    'PFSQRF': (parameters['KLON'], parameters['KLEV']+1, parameters['NBLOCKS']),
    'PFSQSF': (parameters['KLON'], parameters['KLEV']+1, parameters['NBLOCKS']),
    'PICRIT_AER': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'PLCRIT_AER': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'PHRLW': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'PLSM': (parameters['KLON'], parameters['NBLOCKS']),
    'PHRSW': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'PLU': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'PLUDE': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'PMFD': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'PMFU': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'PNICE': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'PRAINFRAC_TOPRFZ': (parameters['KLON'], parameters['NBLOCKS']),
    'PQ': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'PRE_ICE': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'PSNDE': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'PSUPSAT': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'PT': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'PVERVEL': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'PVFA': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'PVFI': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'PVFL': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'tendency_cml_a': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'tendency_cml_cld': (parameters['KLON'], parameters['KLEV'], parameters['NCLV'], parameters['NBLOCKS']),
    'tendency_cml_o3': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'tendency_cml_q': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'tendency_cml_T': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'tendency_cml_u': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'tendency_cml_v': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'tendency_loc_a': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'tendency_loc_cld': (parameters['KLON'], parameters['KLEV'], parameters['NCLV'], parameters['NBLOCKS']),
    'tendency_loc_o3': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'tendency_loc_q': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'tendency_loc_T': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'tendency_loc_u': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'tendency_loc_v': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'tendency_tmp_a': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'tendency_tmp_cld': (parameters['KLON'], parameters['KLEV'], parameters['NCLV'], parameters['NBLOCKS']),
    'tendency_tmp_o3': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'tendency_tmp_q': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'tendency_tmp_T': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'tendency_tmp_u': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'tendency_tmp_v': (parameters['KLON'], parameters['KLEV'], parameters['NBLOCKS']),
    'ZA': (parameters['KLON'], parameters['KLEV']),
    'ZAORIG': (parameters['KLON'], parameters['KLEV']),
    'ZCLDTOPDIST': (parameters['KLON'],),
    'ZCONVSINK': (parameters['KLON'], parameters['NCLV']),
    'ZCONVSRCE': (parameters['KLON'], parameters['NCLV']),
    'ZCORQSICE': (parameters['KLON']),
    'ZCORQSLIQ': (parameters['KLON']),
    'ZCOVPTOT': (parameters['KLON'],),
    'ZDA': (parameters['KLON']),
    'ZCOVPCLR': (parameters['KLON'],),
    'ZCOVPMAX': (parameters['KLON'],),
    'ZDTGDP': (parameters['KLON'],),
    'ZICENUCLEI': (parameters['KLON'],),
    'ZRAINCLD': (parameters['KLON'],),
    'ZSNOWCLD': (parameters['KLON'],),
    'ZDA': (parameters['KLON'],),
    'ZDP': (parameters['KLON'],),
    'ZRHO': (parameters['KLON'],),
    'ZFALLSINK': (parameters['KLON'], parameters['NCLV']),
    'ZFALLSRCE': (parameters['KLON'], parameters['NCLV']),
    'ZFOKOOP': (parameters['KLON'],),
    'ZFLUXQ': (parameters['KLON'], parameters['NCLV']),
    'ZFOEALFA': (parameters['KLON'], parameters['KLEV']+1),
    'ZICECLD': (parameters['KLON'],),
    'ZICEFRAC': (parameters['KLON'], parameters['KLEV']),
    'ZICETOT': (parameters['KLON'],),
    'ZLI': (parameters['KLON'], parameters['KLEV']),
    'ZLIQFRAC': (parameters['KLON'], parameters['KLEV']),
    'ZLNEG': (parameters['KLON'], parameters['KLEV'], parameters['NCLV']),
    'ZPFPLSX': (parameters['KLON'], parameters['KLEV']+1, parameters['NCLV']),
    'ZPSUPSATSRCE': (parameters['KLON'], parameters['NCLV']),
    'ZSOLQA': (parameters['KLON'], parameters['NCLV'], parameters['NCLV']),
    'ZMELTMAX': (parameters['KLON'],),
    'ZQPRETOT': (parameters['KLON'],),
    'ZQSLIQ': (parameters['KLON'], parameters['KLEV']),
    'ZQSICE': (parameters['KLON'], parameters['KLEV']),
    'ZQX': (parameters['KLON'], parameters['KLEV'], parameters['NCLV']),
    'ZQX0': (parameters['KLON'], parameters['KLEV'], parameters['NCLV']),
    'ZQXFG': (parameters['KLON'], parameters['NCLV']),
    'ZQXN': (parameters['KLON'], parameters['NCLV']),
    'ZQXN2D': (parameters['KLON'], parameters['KLEV'], parameters['NCLV']),
    'ZSOLAC': (parameters['KLON'],),
    'ZSUPSAT': (parameters['KLON'],),
    'ZTP1': (parameters['KLON'], parameters['KLEV']),
    # 'DEBUG_EPSILON': (2,),
}



programs = {
    'cloudscexp2_full_20230324': ('CLOUDPROGRAM', 'CLOUDSCOUTER')
}


program_parameters = {
    'cloudscexp2_full_20230324': (
        'NBLOCKS', 'NGPBLKS', 'NUMOMP', 'NGPTOT', 'NGPTOTG', 'NPROMA',
        'KLON', 'KLEV', 'KFLDX', 'LDSLPHY',  'LDMAINCALL',
        'NCLV', 'NCLDQL','NCLDQI','NCLDQR','NCLDQS', 'NCLDQV',
        'LAERLIQAUTOLSP', 'LAERLIQAUTOCP', 'LAERLIQAUTOCPB','LAERLIQCOLL','LAERICESED','LAERICEAUTO',
        'LCLDEXTRA', 'LCLDBUDGET', 'NSSOPT', 'NCLDTOP',
        'NAECLBC', 'NAECLDU', 'NAECLOM', 'NAECLSS', 'NAECLSU', 'NCLDDIAG', 'NAERCLD', 'LAERLIQAUTOLSP',
        'LAERLIQAUTOCP', 'LAERLIQAUTOCPB','LAERLIQCOLL','LAERICESED','LAERICEAUTO', 'NBETA')
}


program_inputs = {
    'cloudscexp2_full_20230324': (
        'PTSPHY','PT', 'PQ',
        'tendency_cml_a', 'tendency_cml_cld', 'tendency_cml_o3', 'tendency_cml_q',
        'tendency_cml_T', 'tendency_cml_u', 'tendency_cml_v',
        'tendency_loc_a', 'tendency_loc_cld', 'tendency_loc_o3', 'tendency_loc_q',
        'tendency_loc_T', 'tendency_loc_u', 'tendency_loc_v',
        'tendency_tmp_a', 'tendency_tmp_cld', 'tendency_tmp_o3', 'tendency_tmp_q',
        'tendency_tmp_T', 'tendency_tmp_u', 'tendency_tmp_v',
        'PVFA', 'PVFL', 'PVFI', 'PDYNA', 'PDYNL', 'PDYNI',
        'PHRSW', 'PHRLW',
        'PVERVEL',  'PAP',      'PAPH',
        'PLSM',     'LDCUM',    'KTYPE',
        'PLU',    'PSNDE',    'PMFU',     'PMFD',
  #!---prognostic fields
        'PA',
        'PCLV',
        'PSUPSAT',
#!-- arrays for aerosol-cloud interactions
#!!! & PQAER,    KAER, &
        'PLCRIT_AER','PICRIT_AER',
        'PRE_ICE',
        'PCCN',     'PNICE',
        'RG', 'RD', 'RCPD', 'RETV', 'RLVTT', 'RLSTT', 'RLMLT', 'RTT', 'RV', 
        'R2ES', 'R3LES', 'R3IES', 'R4LES', 'R4IES', 'R5LES', 'R5IES',
        'R5ALVCP', 'R5ALSCP', 'RALVDCP', 'RALSDCP', 'RALFDCP', 'RTWAT', 'RTICE', 'RTICECU',
        'RTWAT_RTICE_R', 'RTWAT_RTICECU_R', 'RKOOP1', 'RKOOP2',
        'RAMID',
        'RCLDIFF', 'RCLDIFF_CONVI', 'RCLCRIT','RCLCRIT_SEA', 'RCLCRIT_LAND','RKCONV',
        'RPRC1', 'RPRC2','RCLDMAX', 'RPECONS','RVRFACTOR', 'RPRECRHMAX','RTAUMEL', 'RAMIN',
        'RLMIN','RKOOPTAU', 'RCLDTOPP','RLCRITSNOW','RSNOWLIN1', 'RSNOWLIN2','RICEHI1',
        'RICEHI2', 'RICEINIT', 'RVICE','RVRAIN','RVSNOW','RTHOMO','RCOVPMIN', 'RCCN','RNICE',
        'RCCNOM', 'RCCNSS', 'RCCNSU', 'RCLDTOPCF', 'RDEPLIQREFRATE','RDEPLIQREFDEPTH',
        'RCL_KKAac', 'RCL_KKBac', 'RCL_KKAau','RCL_KKBauq', 'RCL_KKBaun',
        'RCL_KK_CLOUD_NUM_SEA', 'RCL_KK_CLOUD_NUM_LAND', 'RCL_AI', 'RCL_BI', 'RCL_CI',
        'RCL_DI', 'RCL_X1I', 'RCL_X2I', 'RCL_X3I','RCL_X4I', 'RCL_CONST1I', 'RCL_CONST2I',
        'RCL_CONST3I', 'RCL_CONST4I','RCL_CONST5I', 'RCL_CONST6I','RCL_APB1','RCL_APB2',
        'RCL_APB3', 'RCL_AS', 'RCL_BS','RCL_CS', 'RCL_DS','RCL_X1S', 'RCL_X2S','RCL_X3S',
        'RCL_X4S', 'RCL_CONST1S', 'RCL_CONST2S', 'RCL_CONST3S', 'RCL_CONST4S',
        'RCL_CONST5S', 'RCL_CONST6S','RCL_CONST7S','RCL_CONST8S','RDENSWAT', 'RDENSREF',
        'RCL_AR','RCL_BR', 'RCL_CR', 'RCL_DR', 'RCL_X1R', 'RCL_X2R', 'RCL_X4R','RCL_KA273',
        'RCL_CDENOM1', 'RCL_CDENOM2','RCL_CDENOM3','RCL_SCHMIDT','RCL_DYNVISC','RCL_CONST1R',
        'RCL_CONST2R', 'RCL_CONST3R', 'RCL_CONST4R', 'RCL_FAC1','RCL_FAC2', 'RCL_CONST5R',
        'RCL_CONST6R', 'RCL_FZRAB', 'RCL_FZRBB',
        'NSHAPEP', 'NSHAPEQ','RBETA','RBETAP1'      
    ),
}


program_outputs = {
    'cloudscexp2_full_20230324': (
        'PLUDE',
    #  !---diagnostic output
        'PCOVPTOT', 'PRAINFRAC_TOPRFZ',
#  !---resulting fluxes
        'PFSQLF',   'PFSQIF' ,  'PFCQNNG',  'PFCQLNG',
        'PFSQRF',   'PFSQSF' ,  'PFCQRNG',  'PFCQSNG',
        'PFSQLTUR', 'PFSQITUR' ,
        'PFPLSL',   'PFPLSN',   'PFHPSL',   'PFHPSN',
        'PEXTRA',
        # 'DEBUG_EPSILON'
    ),
}


def get_inputs(program: str, rng: np.random.Generator) -> Dict[str, Union[Number, np.ndarray]]:
    inp_data = dict()
    for p in program_parameters[program]:
        inp_data[p] = parameters[p]
    for inp in program_inputs[program]:
        if inp not in data:
            print(inp)
            continue
        info = data[inp]
        if isinstance(info, list):
            shape, dtype = info
        else:
            shape = info
            dtype = np.float64
        method = lambda s, d: rng.random(s, d)
        if issubclass(dtype, Integral) or dtype is np.bool_:
            if dtype is np.bool_:
                method = lambda s, d: rng.integers(0, 2, s, d)
                dtype = np.int32
            else:
                method = lambda s, d: rng.integers(0, 10, s, d)
        if shape == (0,):  # Scalar
            inp_data[inp] = method(None, dtype)
        else:
            inp_data[inp] = np.asfortranarray(method(shape, dtype))
    return inp_data


def get_outputs(program: str, rng: np.random.Generator) -> Dict[str, Union[Number, np.ndarray]]:
    out_data = dict()
    for out in program_outputs[program]:
        info = data[out]
        if isinstance(info, list):
            shape, dtype = info
        else:
            shape = info
            dtype = np.float64
        method = lambda s, d: rng.random(s, d)
        if issubclass(dtype, Integral) or dtype is np.bool_:
            if dtype is np.bool_:
                method = lambda s, d: rng.integers(0, 2, s, d)
                dtype = np.int32
            else:
                method = lambda s, d: rng.integers(0, 10, s, d)
        if shape == (0,):  # Scalar
            raise NotImplementedError
        else:
            out_data[out] = np.asfortranarray(method(shape, dtype))
    return out_data


@pytest.mark.skip
def test_program(program: str, device: dace.DeviceType, normalize_offsets: bool):

    fsource = read_source(program)
    program_name, routine_name = programs[program]
    ffunc = get_fortran(fsource, program_name, routine_name)
    sdfg = get_sdfg(fsource, program_name, normalize_offsets)
    if device == dace.DeviceType.GPU:
        auto_optimize(sdfg, device)
    # sdfg.simplify()
    # utils.make_dynamic_map_inputs_unique(sdfg)
    # auto_optimize(sdfg, dace.DeviceType.Generic)

    rng = np.random.default_rng(42)
    inputs = get_inputs(program, rng)
    outputs_f = get_outputs(program, rng)
    outputs_d = copy.deepcopy(outputs_f)

    print("Running Fortran ...")
    ffunc(**{k.lower(): v for k, v in inputs.items()}, **{k.lower(): v for k, v in outputs_f.items()})
    print("Running DaCe ...")
    # sdfg(**inputs, **outputs_d)

    # for k in outputs_f.keys():
    #     farr = outputs_f[k]
    #     darr = outputs_d[k]
    #     if np.allclose(farr, darr):
    #         print(f"{k}: OK!")
    #     else:
    #         print(f"{k}: relative error is {np.linalg.norm(farr - darr) / np.linalg.norm(farr)}")
    #     # assert np.allclose(farr, darr)
    
    # # print(outputs_f['DEBUG_EPSILON'])
    # # print(outputs_d['DEBUG_EPSILON'])
    debug_auto_optimize(sdfg, inputs, outputs_d, outputs_f)


if __name__ == "__main__":
    test_program('cloudscexp2_full_20230324', dace.DeviceType.CPU, False)
