from argparse import ArgumentParser
import os
from subprocess import run

import dace
from dace.config import Config

from utils import use_cache, enable_debug_flags
from execute_utils import run_program, test_program


def main():
    parser = ArgumentParser(description="Run a single program on the GPU")
    parser.add_argument("program", help="Name of the program to run")
    parser.add_argument('--normalize-memlets', action='store_true', default=False)
    parser.add_argument('--cache', action='store_true', default=False, help="Use the cached generated code")
    parser.add_argument('-r', '--repetitions', type=int, default=1, help="Number of repetitions to run")
    parser.add_argument('--only-test', action='store_true', default=False, help="Only test the program")
    parser.add_argument('--debug', action='store_true', default=False, help="Configure for debug build")

    args = parser.parse_args()

    if args.debug:
        enable_debug_flags()

    if args.cache:
        if not use_cache(args.program):
            return 1

    if args.only_test:
        test_program(args.program, device=dace.DeviceType.GPU, normalize_memlets=args.normalize_memlets)
    else:
        run_program(args.program, repetitions=args.repetitions, device=dace.DeviceType.GPU,
                    normalize_memlets=args.normalize_memlets)


if __name__ == '__main__':
    main()
