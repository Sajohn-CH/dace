from argparse import ArgumentParser
import os
from typing import List
import json

from utils.experiments2 import get_experiment_list_df
from measurements.data2 import get_data_wideformat
from scripts2.plot.vert_loop import plot_speedup_array_order, plot_speedup_temp_allocation
from utils.paths import get_plots_2_folder


def plot_vert_loop(experiment_ids: List[int]):
    folder = os.path.join(get_plots_2_folder(), 'vert-loop')
    os.makedirs(folder, exist_ok=True)

    data = get_data_wideformat(experiment_ids).dropna().join(get_experiment_list_df(), on='experiment id')
    index_cols = list(data.index.names)
    index_cols.append('temp allocation')
    index_cols.remove('experiment id')
    data = data.reset_index().set_index(index_cols).drop('experiment id', axis='columns')

    # Create speedup plots
    plot_speedup_array_order(data.copy(), folder)
    plot_speedup_temp_allocation(data.copy(), folder)


def action_script(args):
    scripts = {
            'vert-loop': (plot_vert_loop, {'experiment_ids': [0, 1]})
    }
    function, func_args = scripts[args.script_name]
    additional_args = json.loads(args.args)
    if len(additional_args) > 0:
        func_args.update(json.loads(args.args))
    function(**func_args)


def main():
    parser = ArgumentParser()
    subparsers = parser.add_subparsers(
        title="Commands",
        help="See the help of the respective command")

    script_parser = subparsers.add_parser('script', description='Run predefined script to create a set of pltos')
    script_parser.add_argument('script_name', type=str)
    script_parser.add_argument('--args', type=str, default='{}',
                               help='Additional arguments passed to the plot script function as a json-dictionary')
    script_parser.set_defaults(func=action_script)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
