import numpy as np
import copy
from numbers import Number
from typing import Tuple, Optional, List, Union, Dict
import os
from subprocess import run
import logging

import dace

from execute.parameters import ParametersProvider
from execute.data import set_input_pattern
from utils.general import get_programs_data, read_source, get_fortran, get_sdfg, get_inputs, get_outputs, \
                          compare_output, compare_output_all, optimize_sdfg
from utils.gpu_general import copy_to_device, print_non_zero_percentage
from utils.run_config import RunConfig
from measurements.flop_computation import FlopCount, get_number_of_bytes, get_number_of_flops
from measurements.data import ProgramMeasurement

RNG_SEED = 424388
logger = logging.getLogger(__name__)


# Copied and adapted from tests/fortran/cloudsc.py
def test_program(
        program: str,
        run_config: RunConfig,
        sdfg_file: Optional[str] = None,
        verbose_name: Optional[str] = None,
        print_values: bool = True,
        params: Optional[ParametersProvider] = None) -> bool:
    """
    Tests the given program by comparing the output of the SDFG compiled version to the one compiled directly from
    fortran

    :param program: The program name
    :type program: str
    :param run_config: Configuration how to run it
    :type run_config: RunConfig
    :param sdfg_file: Path to sdfg file. If set will not recreate SDFG but use this one instead, defaults to None
    :type sdfg_file: str, optional
    :param verbose_name: Name of the folder to store any intermediate sdfg. Will only do this if is not None, default
    None
    :type verbose_name: Optional[str]
    :param print_values: If true, will print incorrect values, defaults to true
    :type print_values: bool
    :param params: Parameters to use, if not set will use default testing parameters for this program, defaults to None
    :type params: ParametersProvider
    :return: True if test passes, False otherwise
    :rtype: bool
    """
    assert run_config.device == dace.DeviceType.GPU
    logger.info(str(run_config))

    programs_data = get_programs_data()
    if params is None:
        params = ParametersProvider(program, testing=True)
    fsource = read_source(program)
    program_name = programs_data['programs'][program]
    routine_name = f'{program_name}_routine'
    ffunc = get_fortran(fsource, program_name, routine_name)
    if sdfg_file is None:
        sdfg = get_sdfg(fsource, program_name)
        add_args = {}
        if run_config.specialise_symbols:
            add_args['symbols'] = params.get_dict()
        add_args['k_caching'] = run_config.k_caching
        add_args['change_stride'] = run_config.change_stride
        add_args['verbose_name'] = verbose_name
        add_args['outside_first'] = run_config.outside_loop_first
        add_args['move_assignments_outside'] = run_config.move_assignment_outside

        sdfg = optimize_sdfg(sdfg, run_config.device, use_my_auto_opt=not run_config.use_dace_auto_opt, **add_args)
    else:
        logger.info(f"Reading SDFG from {sdfg_file} and compile it")
        sdfg = dace.sdfg.sdfg.SDFG.from_file(sdfg_file)
        sdfg.compile()

    rng = np.random.default_rng(RNG_SEED)
    inputs = get_inputs(program, rng, params)
    outputs_f = get_outputs(program, rng, params)
    outputs_original = copy.deepcopy(outputs_f)
    np.set_printoptions(precision=3)
    if run_config.pattern is not None:
        set_input_pattern(inputs, outputs_f, params, program, run_config.pattern)
    outputs_d_device = copy_to_device(copy.deepcopy(outputs_f))
    sdfg.validate()
    sdfg.simplify(validate_all=True)

    logger.debug("Run fortran version with parameters: %s", [*list(inputs.keys()), *list(outputs_f.keys())])
    ffunc(**{k.lower(): v for k, v in inputs.items()}, **{k.lower(): v for k, v in outputs_f.items()})
    inputs_device = copy_to_device(inputs)
    logger.debug("Run DaCe version wiht parameters: %s", [*list(inputs_device.keys()), *list(outputs_d_device.keys())])
    sdfg(**inputs_device, **outputs_d_device)

    logger.info(f"{program} ({program_name}) on {run_config.device}: Compare outputs")
    outputs_d = outputs_d_device
    passes_test = compare_output(outputs_f, outputs_d, program, params, print_values=print_values, name_a="Fortran",
                                 name_b="DaCe")
    if compare_output_all(outputs_f, outputs_original, print_if_differ=False, print_values=print_values):
        logger.error("!!! Fortran has not changed any output values !!!")
        passes_test = False
    if compare_output_all(outputs_d, outputs_original, print_if_differ=False, print_values=print_values):
        logger.error("!!! DaCe has not changed any output values !!!")
        passes_test = False

    # passes_test = compare_output_all(outputs_f, outputs_d)

    if passes_test:
        logger.info('Success')
    else:
        logger.error('!!!TEST NOT PASSED!!!')
    return passes_test


def run_program(program: str,  run_config: RunConfig, params: ParametersProvider, repetitions: int = 1,
                sdfg_file: Optional[str] = None, verbose_name: Optional[str] = None):
    """
    Runs Programs

    :param program: Name of the program
    :type program: str
    :param run_config: Configuration how to run it
    :type run_config: RunConfig
    :param parameters: The parameters to use.
    :type parameters: ParametersProvider
    :param repetitions: The number of repetitions to run the program, defaults to 1
    :type repetitions: int, optional
    :param sdfg_file: Path to sdfg file. If set will not recreate SDFG but use this one instead, defaults to None
    :type sdfg_file: str, optional
    :param verbose_name: Name of the folder to store any intermediate sdfg. Will only do this if is not None, default
    None
    :type verbose_name: Optional[str]
    """
    programs = get_programs_data()['programs']
    logger.info(f"run {program} ({programs[program]}) for {repetitions} time on device {run_config.device}")
    logger.info(str(run_config))
    fsource = read_source(program)
    program_name = programs[program]
    if sdfg_file is None:
        sdfg = get_sdfg(fsource, program_name)
        additional_args = {}
        if run_config.specialise_symbols:
            additional_args['symbols'] = params.get_dict()
        additional_args['k_caching'] = run_config.k_caching
        additional_args['change_stride'] = run_config.change_stride
        additional_args['verbose_name'] = verbose_name
        additional_args['outside_first'] = run_config.outside_loop_first
        additional_args['move_assignments_outside'] = run_config.move_assignment_outside

        sdfg = optimize_sdfg(sdfg, run_config.device, use_my_auto_opt=not run_config.use_dace_auto_opt,
                             **additional_args)
    else:
        logger.info(f"Reading SDFG from {sdfg_file} and compile it")
        sdfg = dace.sdfg.sdfg.SDFG.from_file(sdfg_file)
        sdfg.compile()

    rng = np.random.default_rng(RNG_SEED)
    inputs = get_inputs(program, rng, params)
    inputs = copy_to_device(inputs)
    outputs = copy_to_device(get_outputs(program, rng, params))
    if run_config.pattern is not None:
        set_input_pattern(inputs, outputs, params, program, run_config.pattern)

    for _ in range(repetitions):
        sdfg(**inputs, **outputs)


def compile_for_profile(program: str, params: Union[ParametersProvider, Dict[str, Number]],
                        run_config: RunConfig) -> dace.SDFG:
    """
    Compile the given program for profiliation. Meaning a total runtime timer is added

    :param program: Name of the program
    :type program: str
    :param params: The parameters to use.
    :type params: Union[ParametersProvider, Dict[str, Number]]
    :param run_config: Configuration how to run it
    :type run_config: RunConfig
    :return: Generated SDFG
    :rtype: dace.SDFG
    """
    programs = get_programs_data()['programs']
    fsource = read_source(program)
    program_name = programs[program]
    sdfg = get_sdfg(fsource, program_name)
    add_args = {}
    params_dict = params
    if isinstance(params, ParametersProvider):
        params_dict = params.get_dict()
    if run_config.specialise_symbols:
        add_args['symbols'] = params_dict
    add_args['k_caching'] = run_config.k_caching
    add_args['change_stride'] = run_config.change_stride
    add_args['outside_first'] = run_config.outside_loop_first
    add_args['move_assignments_outside'] = run_config.move_assignment_outside
    sdfg = optimize_sdfg(sdfg, run_config.device, use_my_auto_opt=not run_config.use_dace_auto_opt, **add_args)

    sdfg.instrument = dace.InstrumentationType.Timer
    sdfg.compile()
    return sdfg


def profile_program(program: str, run_config: RunConfig, params: ParametersProvider,
                    repetitions=10) -> ProgramMeasurement:

    results = ProgramMeasurement(program, params)

    programs = get_programs_data()['programs']
    logger.info(f"Profile {program}({programs[program]}) rep={repetitions}")
    routine_name = f"{programs[program]}_routine"

    sdfg = compile_for_profile(program, params, run_config)

    rng = np.random.default_rng(RNG_SEED)
    inputs = get_inputs(program, rng, params)
    outputs = get_outputs(program, rng, params)
    if run_config.pattern is not None:
        set_input_pattern(inputs, outputs, params, program, run_config.pattern)

    sdfg.clear_instrumentation_reports()
    logger.info("Measure total runtime")
    inputs = copy_to_device(inputs)
    outputs = copy_to_device(outputs)
    for i in range(repetitions):
        sdfg(**inputs, **outputs)

    # variables = {'cloudsc_class2_781': 'ZLIQFRAC', 'cloudsc_class2_1762': 'ZSNOWCLD2',
    #              'cloudsc_class2_1516': 'ZCLDTOPDIST2', 'my_test': 'ARRAY_A'}
    # print_non_zero_percentage(outputs, variables[program])
    reports = sdfg.get_instrumentation_reports()

    results.add_measurement("Total time", "ms")
    for report in reports:
        keys = list(report.durations[(0, -1, -1)][f"SDFG {routine_name}"].keys())
        key = keys[0]
        if len(keys) > 1:
            logger.warning(f"Report has more than one key, taking only the first one. keys: {keys}")
        results.add_value("Total time",
                          float(report.durations[(0, -1, -1)][f"SDFG {routine_name}"][key][0]))

    return results


def get_roofline_data(program: str, params: ParametersProvider,
                      pattern: Optional[str] = None) -> Tuple[FlopCount, Number]:
    rng = np.random.default_rng(RNG_SEED)
    inputs = get_inputs(program, rng, params)
    outputs = get_outputs(program, rng, params)
    if pattern is not None:
        set_input_pattern(inputs, outputs, params, program, pattern)
    flop_count = get_number_of_flops(params, inputs, outputs, program)
    bytes = get_number_of_bytes(params, inputs, outputs, program)
    return (flop_count, bytes)


def get_command_args_single_run(program: str, run_config: RunConfig) -> List[str]:
    """
    Gets the commands required to run the given program with the given config once.

    :param program: The name of the program
    :type program: str
    :param run_config: The desired config to run it with
    :type run_config: RunConfig
    :return: List of commands, as required to subprocess.run
    :rtype: List[str]
    """
    test_program_path = os.path.join(os.path.split(os.path.dirname(__file__))[0], 'run_program.py')
    command_program = ['python3', test_program_path, program, '--repetitions', '1']
    if run_config.use_dace_auto_opt:
        command_program.append('--use-dace-auto-opt')
    if run_config.pattern is not None:
        command_program.extend(['--pattern', run_config.pattern])
    return command_program


def gen_ncu_report(program: str, report_filename: str, run_config: RunConfig, ncu_args: List[str] = [],
                   program_args: List[str] = []) -> bool:
    """
    Generates a ncu report into the given report filename using the given additional ncu arguments

    :param program: The name of the program to profile using ncu
    :type program: str
    :param report_filename: The path to where the report should be save
    :type report_filename: str
    :param run_config: The config to run the given program with
    :type run_config: RunConfig
    :param ncu_args: Any additional arguments for ncu, optional
    :type ncu_args: List[str]
    :param program_args: Any additional arguments for the program, optional
    :type program_args: List[str]
    :return: True if ncu report was successfully created, False otherwise
    :rtype: bool
    """
    logger.info(f"Create ncu report and save it into {report_filename}")
    command_program = get_command_args_single_run(program, run_config)
    command_program.extend(program_args)
    ncu_command = ['ncu', '--force-overwrite', '--export', report_filename, *ncu_args]
    logger.info(f"command: {' '.join(ncu_command)} {' '.join(command_program)}")
    ncu_output = run([*ncu_command, *command_program], capture_output=True)
    if ncu_output.returncode != 0:
        logger.error("Failed to run the program with ncu")
        logger.error(ncu_output.stdout.decode('UTF-8'))
        logger.error(ncu_output.stderr.decode('UTF-8'))
        return False
    return True


def gen_nsys_report(program: str, report_filename: str, run_config: RunConfig) -> bool:
    """
    Generates a nsys report and saves it into the given report filename.

    :param program: The name of the program to profile using ncu
    :type program: str
    :param report_filename: The path to where the report should be save
    :type report_filename: str
    :param run_config: The config to run the given program with
    :type run_config: RunConfig
    :return: True if ncu report was successfully created, False otherwise
    :rtype: bool
    """
    logger.info(f"Create nsys report and save it into {report_filename}")
    command_nsys = ['nsys', 'profile', '--force-overwrite', 'true', '--output', report_filename]
    command_program = get_command_args_single_run(program, run_config)
    nsys_output = run([*command_nsys, *command_program], capture_output=True)
    if nsys_output.returncode != 0:
        logger.error("Failed to run the program with nsys")
        logger.error(nsys_output.stdout.decode('UTF-8'))
        logger.error(nsys_output.stderr.decode('UTF-8'))
        return False
    return True
