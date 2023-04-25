from argparse import ArgumentParser
from subprocess import run
import csv
import os
from typing import Dict
from tabulate import tabulate
import sys
import re

from utils import convert_to_bytes
from print_utils import sort_by_program_number
from ncu_utils import get_all_actions, get_achieved_performance, get_achieved_work, get_achieved_bytes, \
                      get_peak_performance, action_list_to_dict

sys.path.insert(0, '/apps/ault/spack/opt/spack/linux-centos8-zen/gcc-8.4.1/cuda-11.8.0-fjdnxm6yggxxp75sb62xrxxmeg4s24ml/nsight-compute-2022.3.0/extras/python/')
import ncu_report


def main():
    parser = ArgumentParser(description='TODO')
    parser.add_argument('basename')
    parser.add_argument('--name-regex', type=str, default=None, help="Regex to match kernel names against")
    parser.add_argument('--with-runtime', action='store_true', default=False)
    parser.add_argument('--detail', action='store_true', default=False)

    args = parser.parse_args()

    folder = 'ncu-reports'
    flat_data = []
    flat_data_detail_flop = []
    flat_data_detail_memory = []
    headers = ['program', 'Q [byte]', 'W [flop]', 'I [Flop/byte]', 'P [flop/s]', 'beta [byte/s]',
               'peak P [flop/s]', 'peak beta [byte/s]', 'Performance [%]', 'Bandwidth [%]']
    floatfmt = [None, None, None, ".3f", ".1E", ".1E", ".1E", ".1E", ".1f", ".1f"]
    headers_detail_flop = ['program', 'double W', 'dadds', 'dmuls', 'dfmas', 'float W', 'fadds', 'fmuls', 'ffmas']
    headers_detail_memory = ['program', 'global total', 'global written', 'global read']

    if args.with_runtime:
        headers.append('Runtime [s]')
        floatfmt.append(".3E")
    for filename in os.listdir(folder):
        if filename.startswith(f"report_{args.basename}"):
            path = os.path.join(folder, filename)
            if len(filename.split(f"report_{args.basename}_")) == 1:
                program = filename
            else:
                program = filename.split(f"report_{args.basename}_")[1].split(".")[0]
            actions = action_list_to_dict(get_all_actions(path))
            if len(actions) > 1 and 'Kernel name' not in headers:
                headers.insert(1, 'Kernel name')
                headers_detail_flop.insert(1, 'Kernel name')
                headers_detail_memory.insert(1, 'Kernel name')
                floatfmt.insert(1, None)

            for name in actions:
                if args.name_regex is not None:
                    if re.match(args.name_regex, name) is None:
                        continue
                # always take the last action
                action = actions[name][-1]
                achieved_work = get_achieved_work(action)
                Q = get_achieved_bytes(action)
                peak = get_peak_performance(action)
                achieved_performance = get_achieved_performance(action)
                row = [program, int(Q), int(achieved_work['dW']), achieved_work['dW'] / Q,
                       achieved_performance[0], achieved_performance[1],
                       peak[0], peak[1],
                       achieved_performance[0] / peak[0] * 100, achieved_performance[1] / peak[1] * 100]
                if args.with_runtime:
                    runtime = action.metric_by_name('gpu__time_duration.sum').as_double() * 1e9
                    row.append(runtime)

                if args.detail:
                    flop_row = [program, *[achieved_work[key] for key in ['dW', 'dadds', 'dmuls', 'dfmas', 'fW',
                                                                          'fadds', 'fmuls', 'ffmas']]]
                    memory_row = [program, Q, action.metric_by_name('dram__bytes_write.sum').as_uint64(),
                                  action.metric_by_name('dram__bytes_read.sum').as_uint64()]

                if len(actions) > 1:
                    row.insert(1, name)
                    if args.detail:
                        flop_row.insert(1, name)

                flat_data.append(row)
                if args.detail:
                    flat_data_detail_flop.append(flop_row)
                    flat_data_detail_memory.append(memory_row)

    sort_by_program_number(flat_data)
    print(tabulate(flat_data, headers=headers, intfmt=',',
                   floatfmt=floatfmt))
    if args.detail:
        print()
        print("Work detail (in flop)")
        print(tabulate(flat_data_detail_flop, headers=headers_detail_flop, intfmt=','))
        print()
        print("Memory detail (in bytes)")
        print(tabulate(flat_data_detail_memory, headers=headers_detail_memory, intfmt=','))


if __name__ == '__main__':
    main()
