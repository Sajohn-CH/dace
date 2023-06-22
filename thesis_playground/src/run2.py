from argparse import ArgumentParser
import os
import shutil
from subprocess import check_output
from numbers import Number
from typing import Optional, Union, List, Tuple
from datetime import datetime
import numpy as np
import pandas as pd
import json

from utils.print import print_dataframe, print_with_time
from utils.execute_dace import RunConfig, gen_ncu_report, test_program
from utils.paths import get_results_2_folder, get_thesis_playground_root_dir, get_experiments_2_file
from utils.experiments2 import get_experiment_list_df
from execute.parameters import ParametersProvider
from measurements.profile_config import ProfileConfig
from measurements.data2 import get_data_wideformat, average_data


def do_vertical_loops(additional_desc: Optional[str] = None, nblock_min: Number = 1e5, nblock_max: Number = 6e5,
                      nblock_step: Number = 1e5):
    programs = [
            'cloudsc_vert_loop_4_ZSOLQA',
            'cloudsc_vert_loop_6_ZSOLQA',
            'cloudsc_vert_loop_6_1_ZSOLQA',
            'cloudsc_vert_loop_7_3'
            ]
    profile_configs = []
    for program in programs:
        test_program(program, RunConfig())
        params_list = []
        for nblock in np.arange(nblock_max, nblock_min, -nblock_step):
            params = ParametersProvider(program,
                                        update={'NBLOCKS': int(nblock), 'KLEV': 137, 'KFDIA': 1, 'KIDIA': 1, 'KLON': 1})
            params_list.append(params)
        profile_configs.append(ProfileConfig(program, params_list, ['NBLOCKS'], ncu_repetitions=1,
                                             tot_time_repetitions=5))

    experiment_desc = "Vertical loops with ZSOLQA"
    if additional_desc is not None:
        experiment_desc += f" with {additional_desc}"
    print_with_time("[run2::do_vertical_loops] run stack profile")
    profile(profile_configs, RunConfig(), experiment_desc, [('temp allocation', 'stack')], ncu_report=True)
    for profile_config in profile_configs:
        profile_config.set_heap_limit = True
        profile_config.heap_limit_str = "(KLON * (NCLV - 1)) + KLON * NCLV * (NCLV - 1) + KLON * (NCLV - 1) +" + \
                                        "KLON * (KLEV - 1) + 4 * KLON"
    print_with_time("[run2::do_vertical_loops] run heap profile")
    profile(profile_configs, RunConfig(specialise_symbols=False), experiment_desc, [('temp allocation', 'heap')],
            ncu_report=True)


base_experiments = {
    'vert-loop': do_vertical_loops
}


def profile(program_configs: List[ProfileConfig], run_config: RunConfig, experiment_description: str,
            additional_columns: List[Tuple[str, Union[Number, str]]] = [], ncu_report: bool = True,
            append_to_last_experiment: bool = False):
    """
    Profile the given programs with the given configurations

    :param program_configs: The profile configurations to use
    :type program_configs: List[ProfileConfig]
    :param run_config: The run configuration to use. Same configuration for every profiling run
    :type run_config: RunConfig
    :param experiment_description: The description of this experiment
    :type experiment_description: str
    :param additional_columns: List of any additional columns to add to the experiments database. Contains a tuple for
    each column. First is key, then value, defaults to []
    :type additional_columns: List[Tuple[str, Union[Number, str]]], optional
    :param ncu_report: If a full ncu report should be created and stored, defaults to True
    :type ncu_report: bool
    :param append_to_last_experiment: Set to true the experiment id should be the same as the last one. Use carefully.
    Should only be used when calling this function twice consecutively. Will not write to experiments.csv is set to
    True. defaults to False.
    :type append_to_last_experiment: bool
    """
    experiment_list_df = get_experiment_list_df()
    if 'experiment id' in experiment_list_df.reset_index().columns and len(experiment_list_df.index) > 0:
        if append_to_last_experiment:
            new_experiment_id = experiment_list_df.reset_index()['experiment id'].max()
        else:
            new_experiment_id = experiment_list_df.reset_index()['experiment id'].max() + 1
    else:
        new_experiment_id = 0

    if not append_to_last_experiment:
        git_hash = check_output(['git', 'rev-parse', '--short', 'HEAD'], cwd=get_thesis_playground_root_dir())\
            .decode('UTF-8').replace('\n', '')
        node = check_output(['uname', '-a']).decode('UTF-8').split(' ')[1].split('.')[0]
        this_experiment_data = {
            'experiment id': new_experiment_id,
            'description': experiment_description,
            'git hash': git_hash, 'node': node,
            'datetime': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        for key, value in additional_columns:
            this_experiment_data.update({key: value})
        experiment_list_df = pd.concat([experiment_list_df,
                                       pd.DataFrame([this_experiment_data]).set_index(['experiment id'])])
        experiment_list_df.to_csv(get_experiments_2_file())

    for program_config in program_configs:
        experiment_folder = os.path.join(get_results_2_folder(), program_config.program, str(new_experiment_id))
        os.makedirs(experiment_folder, exist_ok=True)
        additional_columns_values = [col[1] for col in additional_columns]

        # Generate SDFG only once -> save runtime
        # sdfg_name = f"{program_config.program}_{new_experiment_id}_" + '_'.join(additional_columns_values) + ".sdfg"
        # sdfg_path = os.path.join(experiment_folder, sdfg_name)
        # print_with_time(f"[run2::profile] Generate SDFG and save it into {sdfg_path}")
        # sdfg = program_config.compile(program_config.sizes[0], run_config, specialise_changing_sizes=False)
        # sdfg.save(sdfg_path)
        additional_args = {}
        # additional_args['sdfg_path'] = sdfg_path
        if ncu_report:
            additional_args['ncu_report_path'] = f"{program_config.program}_{new_experiment_id}_" + \
                                                 '_'.join(additional_columns_values) + \
                                                 ".ncu-rep"
        program_config.profile(run_config, **additional_args).to_csv(os.path.join(experiment_folder, 'results.csv'))
        for index, params in enumerate(program_config.sizes):
            with open(os.path.join(experiment_folder, f"{index}_params.json"), 'w') as file:
                json.dump(params.get_dict(), file)


def action_profile(args):
    function_args = json.loads(args.args)
    base_experiments[args.base_exp](**function_args)


def action_print(args):
    columns = {
            'experiment id': ('Exp ID', ','),
            'node': ('Node', None),
            'program': ('Program', None),
            'NBLOCKS': ('NBLOCKS', ','),
            'runtime': ('T [s]', '.3e'),
            'measured bytes': ('D [b]', '.3e'),
            'theoretical bytes total': ('Q [b]', '.3e')
    }

    df = get_data_wideformat(args.experiment_ids).dropna()
    df = average_data(df).reset_index().join(get_experiment_list_df(), on='experiment id')
    print_dataframe(columns, df.reset_index(), args.tablefmt)


def action_list_experiments(args):
    columns = {
            'experiment id': ('Exp ID', ','),
            'description': ('Description', None),
            'node': ('Node', None),
            'datetime': ('Date', None)
            }
    print_dataframe(columns, get_experiment_list_df().reset_index(), args.tablefmt)


def action_remove_experiment(args):
    experiment_ids = []
    if args.all_to is None:
        experiment_ids = [args.experiment_id]
    else:
        experiment_ids = np.arange(args.experiment_id, args.all_to+1)
    for experiment_id in experiment_ids:
        for program_dir in os.listdir(get_results_2_folder()):
            program_dir = os.path.join(get_results_2_folder(), program_dir)
            exp_dir = os.path.join(program_dir, str(experiment_id))
            if os.path.exists(exp_dir):
                print(f"Remove {exp_dir}")
                shutil.rmtree(exp_dir)
        experiments = get_experiment_list_df().drop(int(experiment_id), axis='index')
        experiments.to_csv(get_experiments_2_file())


def main():
    parser = ArgumentParser()
    subparsers = parser.add_subparsers(
        title="Commands",
        help="See the help of the respective command")

    profile_parser = subparsers.add_parser('profile', description='Execute a profiling run')
    profile_parser.add_argument('base_exp', choices=base_experiments.keys(),
                                help='Name of the base experiment to use')
    profile_parser.add_argument('--args', type=str, default='{}',
                                help='Additional arguments passed to the base experiment function as a json-dictionary')
    profile_parser.set_defaults(func=action_profile)

    print_parser = subparsers.add_parser('print', description='Print selected data')
    print_parser.add_argument('experiment_ids', nargs='+', help='Ids of experiments to print')
    print_parser.add_argument('--tablefmt', default='plain', help='Table format for tabulate')
    print_parser.set_defaults(func=action_print)

    list_experiments_parser = subparsers.add_parser('list-experiments', description='List experiments')
    list_experiments_parser.add_argument('--tablefmt', default='plain', help='Table format for tabulate')
    list_experiments_parser.set_defaults(func=action_list_experiments)

    remove_experiment_parser = subparsers.add_parser('remove-experiment', description='Remove experiment')
    remove_experiment_parser.add_argument('experiment_id', type=int)
    remove_experiment_parser.add_argument('--all-to', type=int, default=None,
                                          help="Delete all experiment ids from the first given to (inlcuding) this")
    remove_experiment_parser.set_defaults(func=action_remove_experiment)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
