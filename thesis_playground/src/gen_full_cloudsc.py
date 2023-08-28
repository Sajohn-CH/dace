from argparse import ArgumentParser
import logging
from datetime import datetime
import os

from utils.generate_sdfg import get_optimised_sdfg
from utils.general import remove_build_folder
from utils.log import setup_logging
from utils.execute_dace import RunConfig
from utils.paths import get_full_cloudsc_log_dir
from execute.parameters import ParametersProvider

logger = logging.getLogger(__name__)


def main():
    parser = ArgumentParser()
    parser.add_argument('--version', default=2, type=int)
    parser.add_argument('--baseline', action='store_true', default=False)
    parser.add_argument('--log-level', default='info')
    args = parser.parse_args()

    if args.version == 3:
        program = 'cloudscexp3'
    else:
        program = 'cloudscexp2'

    logfile = os.path.join(get_full_cloudsc_log_dir(), f"{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}_{program}.log")
    setup_logging(level=args.log_level.upper(), logfile=logfile, full_logfile=f"{logfile}.all")
    logger.info("Use program: %s", program)

    params = ParametersProvider(program, update={'NBLOCKS': 16384})
    if args.baseline:
        run_config = RunConfig(k_caching=False, change_stride=False, outside_loop_first=False,
                               move_assignment_outside=False)
    else:
        run_config = RunConfig(k_caching=True, change_stride=True, outside_loop_first=False)
    logger.debug(run_config)
    remove_build_folder(program)
    sdfg = get_optimised_sdfg(program, run_config, params, ['NBLOCKS'], instrument=False, storage_on_gpu=False)
    sdfg.compile()
    sdfg.save(os.path.join(get_full_cloudsc_log_dir(), f"{program}.sdfg"))
    with open(os.path.join(get_full_cloudsc_log_dir(), f"signature_dace_{program}.txt"), 'w') as file:
        file.write(sdfg.signature())


if __name__ == '__main__':
    main()
