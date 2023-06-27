import os
from typing import Optional
import pandas as pd
import seaborn as sns

from utils.data_analysis import compute_speedups
from utils.experiments2 import get_program_infos
from utils.plot import save_plot, get_new_figure, size_vs_y_plot, get_bytes_formatter, legend_on_lines, \
                       get_arrowprops, replace_legend_names

hue_order = ['cloudsc_vert_loop_4_ZSOLQA', 'cloudsc_vert_loop_6_ZSOLQA', 'cloudsc_vert_loop_6_1_ZSOLQA',
             'cloudsc_vert_loop_7_3']


def plot_speedup_array_order(avg_data: pd.DataFrame, folder: str, legend_on_line: bool = False):
    """
    Plots speedup of kernel runtime copmaring the different array layouts on heap allocation

    :param avg_data: Averaged data used to compute speedup
    :type avg_data: pd.DataFrame
    :param folder: The folder to store the plot in
    :type folder: str
    :param legend_on_line: If legend should be put on lines, defaults to False
    :type legend_on_line: bool, optional
    """
    # Create subplots
    figure = get_new_figure(4)
    ax = figure.add_subplot(1, 1, 1)
    ax.axhline(y=1, color='gray', linestyle='--')
    # figure.suptitle(f"Vertical Loop Programs run on {node} using NVIDIA {gpu} averaging {run_count_str} runs")

    speedups = compute_speedups(avg_data, ('cloudsc_vert_loop_4_ZSOLQA'), ('program')) \
        .drop(index='stack', level='temp allocation')\
        .drop(index='cloudsc_vert_loop_4_ZSOLQA', level='program')\
        .reset_index()

    size_vs_y_plot(ax, 'Speedup', 'Speedup of kernel runtime achieved using different array layouts compared to original', speedups,
                   size_var_name='NBLOCKS')
    sns.lineplot(data=speedups, x='NBLOCKS', y='runtime', hue='program', ax=ax, marker='o', hue_order=hue_order)
    program_names_map = get_program_infos()['full description'].to_dict()
    if legend_on_line:
        legend_on_line(ax, ((300000, 1.2), (250000, 6.3), (350000, 7.5)), [program_names_map[p] for p in hue_order[1:]],
                       rotations=[0, -12, -15], color_palette_offset=1)
    else:
        replace_legend_names(ax.get_legend(), program_names_map)
    save_plot(os.path.join(folder, 'speedup_array_order.pdf'))


def plot_speedup_temp_allocation(avg_data: pd.DataFrame, folder: str, legend_on_line: bool = False):
    """
    Plots speedup of kernel runtime, comparing the different temporary array allocation

    :param avg_data: Averaged data used to compute the speedup
    :type avg_data: pd.DataFrame
    :param folder: The folder to store the plot in
    :type folder: str
    :param legend_on_line: If legend should be put on lines, defaults to False
    :type legend_on_line: bool, optional
    """
    figure = get_new_figure(4)
    ax = figure.add_subplot(1, 1, 1)
    ax.axhline(y=1, color='gray', linestyle='--')
    # figure.suptitle(f"Vertical Loop Programs run on {node} using NVIDIA {gpu} averaging {run_count_str} runs")

    speedups = compute_speedups(avg_data, ('heap'), ('temp allocation')) \
        .drop(index='heap', level='temp allocation') \
        .reset_index()

    sns.lineplot(data=speedups, hue='program', x='NBLOCKS', y='runtime', ax=ax, marker='o', hue_order=hue_order)
    size_vs_y_plot(ax, 'Speedup', 'Speedup of kernel runtime stack allocation vs heap allocation', speedups, size_var_name='NBLOCKS')
    program_names_map = get_program_infos()['full description'].to_dict()
    if legend_on_line:
        legend_on_line(ax, ((1.5e5, 30), (4e5, 350), ((4e5, 120), (4.5e5, 45)), ((3e5, 200), (2e5, 85))),
                       [program_names_map[p] for p in hue_order], rotations=[-3, -10, 0, 0])
    else:
        replace_legend_names(ax.get_legend(), program_names_map)
    save_plot(os.path.join(folder, 'speedup_temp_allocation.pdf'))


def plot_runtime(data: pd.DataFrame, folder: str, legend_on_line: bool = False,
                 limit_temp_allocation_to: Optional[str] = None):
    """
    Plot the kernel runtime

    :param data: The data to plot
    :type data: pd.DataFrame
    :param folder: The folder to store the plot in
    :type folder: str
    :param legend_on_line: If legend should be put on lines, defaults to False
    :type legend_on_line: bool, optional
    :param limit_temp_allocation_to: The temporary array allocation the data should be limited to (either 'heap',
            'stack' or None. If None does not limit it, defaults to None
    :type limit_temp_allocation_to: Optional[str], optional
    """
    temp_allocations = ['stack', 'heap']
    if limit_temp_allocation_to is not None and limit_temp_allocation_to in temp_allocations:
        title = f"Kernel Runtimes of {limit_temp_allocation_to} allocated versions"
        data = data.xs(limit_temp_allocation_to, level='temp allocation')
        filename = f"runtime_{limit_temp_allocation_to}.pdf"
    else:
        title = "Kernel Runtimes"
        filename = "runtime.pdf"

    figure = get_new_figure(4)
    ax = figure.add_subplot(1, 1, 1)
    # figure.suptitle(f"Vertical Loop Programs run on {node} using NVIDIA {gpu} averaging {run_count_str} runs")
    size_vs_y_plot(ax, 'Runtime [s]', title, data, size_var_name='NBLOCKS')
    additional_args = {}
    if limit_temp_allocation_to == 'stack':
        dashes = {program: '' for program in data.reset_index()['program'].unique()}
        dashes['cloudsc_vert_loop_6_1_ZSOLQA'] = (2, 2)
        additional_args['linewidth'] = 3
        additional_args['dashes'] = dashes
        additional_args['style'] = 'program'
    elif limit_temp_allocation_to is None:
        additional_args['style'] = 'temp allocation'

    sns.lineplot(data, x='NBLOCKS', y='runtime', hue='program', ax=ax, hue_order=hue_order, errorbar=('ci', 95),
                 err_style='bars', **additional_args)
    program_names_map = get_program_infos()['full description'].to_dict()
    if legend_on_line:
        legend_on_line(ax, ((3e5, 0.084), (1.8e5, 0.009), (3.8e5, 0.015), (3.8e5, 0.005)),
                       [program_names_map[p] for p in hue_order], rotations=[25, 3, 3, 3])
    else:
        replace_legend_names(ax.get_legend(), program_names_map)
    save_plot(os.path.join(folder, filename))


def plot_memory_transfers(data: pd.DataFrame, folder: str, legend_on_line: bool = False,
                          limit_temp_allocation_to: Optional[str] = None):
    """
    Plot the memory transfers

    :param data: The data to plot
    :type data: pd.DataFrame
    :param folder: The folder to store the plot in
    :type folder: str
    :param legend_on_line: If legend should be put on lines, defaults to False
    :type legend_on_line: bool, optional
    :param limit_temp_allocation_to: The temporary array allocation the data should be limited to (either 'heap',
            'stack' or None. If None does not limit it, defaults to None
    :type limit_temp_allocation_to: Optional[str], optional
    """
    temp_allocations = ['stack', 'heap']
    if limit_temp_allocation_to is not None and limit_temp_allocation_to in temp_allocations:
        title = f"Measured Transferred Bytes of {limit_temp_allocation_to} allocated versions"
        data = data.xs(limit_temp_allocation_to, level='temp allocation')
        filename = f"memory_{limit_temp_allocation_to}.pdf"
    else:
        title = "Measured Transferred Bytes"
        filename = "memory.pdf"

    figure = get_new_figure(4)
    ax = figure.add_subplot(1, 1, 1)
    # figure.suptitle(f"Vertical Loop Programs run on {node} using NVIDIA {gpu} averaging {run_count_str} runs")
    size_vs_y_plot(ax, 'Transferred to/from global memory [byte]', title, data, size_var_name='NBLOCKS')
    additional_args = {}
    if limit_temp_allocation_to == 'stack':
        # dashes = {program: '' for program in data.reset_index()['program'].unique()}
        # dashes['cloudsc_vert_loop_6_1_ZSOLQA'] = (2, 2)
        # additional_args['linewidth'] = 3
        # additional_args['dashes'] = dashes
        # additional_args['style'] = 'program'
        pass
    elif limit_temp_allocation_to is None:
        additional_args['style'] = 'temp allocation'

    sns.lineplot(data, x='NBLOCKS', y='measured bytes', hue='program', ax=ax, hue_order=hue_order, errorbar=('ci', 95),
                 err_style='bars', **additional_args)
    program_names_map = get_program_infos()['full description'].to_dict()
    if legend_on_line:
        legend_on_line(ax, ((3e5, 0.084), (1.8e5, 0.009), (3.8e5, 0.015), (3.8e5, 0.005)),
                       [program_names_map[p] for p in hue_order], rotations=[25, 3, 3, 3])
    else:
        replace_legend_names(ax.get_legend(), program_names_map)
    save_plot(os.path.join(folder, filename))
