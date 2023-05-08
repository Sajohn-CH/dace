from argparse import ArgumentParser

import dace

from utils.general import get_programs_data, save_graph, get_sdfg, reset_graph_files, read_source, enable_debug_flags
from my_auto_opt import auto_optimize


def main():
    parser = ArgumentParser()
    parser.add_argument('program', type=str, help='Name of the program to generate the SDFGs of')
    parser.add_argument(
        '--only-graph',
        action='store_true',
        help='Does not compile the SDFGs into C++ code, only creates the SDFGs and runs the transformations')
    parser.add_argument('--debug', action='store_true', default=False, help="Configure for debug build")

    device = dace.DeviceType.GPU
    args = parser.parse_args()

    if args.debug:
        enable_debug_flags()

    reset_graph_files(args.program)

    programs = get_programs_data()['programs']
    fsource = read_source(args.program)
    program_name = programs[args.program]
    sdfg = get_sdfg(fsource, program_name)

    for k, v in sdfg.arrays.items():
        if not v.transient and type(v) == dace.data.Array:
            v.storage = dace.dtypes.StorageType.GPU_Global

    save_graph(sdfg, args.program, "before_auto_opt")
    auto_optimize(sdfg, device, program=args.program)
    save_graph(sdfg, args.program, "after_auto_opt")
    sdfg.instrument = dace.InstrumentationType.Timer
    if not args.only_graph:
        sdfg.compile()
    return sdfg


if __name__ == '__main__':
    main()
