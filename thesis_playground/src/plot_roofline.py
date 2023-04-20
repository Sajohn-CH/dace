from argparse import ArgumentParser
import json
from os import path
from typing import Dict, Tuple, Optional
from numbers import Number
import matplotlib.pyplot as plt
import matplotlib
import math

from utils import get_results_dir, convert_to_seconds
from measurement_data import MeasurementRun, Measurement
from flop_computation import FlopCount, read_roofline_data


def draw_roofline(ax: matplotlib.axis.Axis, peak_performance: float, max_bandwidth: float, max_bandwidth_unit: str,
                  min_intensity: float, max_intensity: float, color: str, bandwidth_label: Optional[str]):
    crosspoint_intensity = peak_performance / max_bandwidth
    if max_intensity < crosspoint_intensity:
        max_intensity = crosspoint_intensity*2.0
    ax.loglog([min_intensity, crosspoint_intensity], [max_bandwidth * (min_intensity), peak_performance], color=color)
    ax.loglog([crosspoint_intensity, max_intensity], [peak_performance, peak_performance], color=color)
    dx = crosspoint_intensity-min_intensity
    dy = peak_performance-max_bandwidth*min_intensity
    angle = math.atan(dy/dx)*180/math.pi
    text = f"beta={max_bandwidth:.3e} [{max_bandwidth_unit}]"
    if bandwidth_label is not None:
        text += f" ({bandwidth_label})"
    ax.text(min_intensity, max_bandwidth*min_intensity, text, rotation=angle,
            rotation_mode='anchor', transform_rotates_text=True)


def draw_program_points(measurement: Measurement, label: str, ax: matplotlib.axis.Axis,
                        flop_count: FlopCount, byte_count: Number) -> Number:
    """
    Draws point of the given measurement onto the given axis

    :param measurement: The measurement
    :type measurement: Measurement
    :param label: The label of the measurement
    :type label: str
    :param ax: The
    :type ax: matplotlib.axis.Axis
    :param flop_count: The FlopCount object
    :type flop_count: FlopCount
    :param byte_count: The number of bytes transferred
    :type byte_count: Number
    :return: The operational intensity
    :rtype: Number
    """
    time = measurement.average()
    if measurement.unit.endswith('second'):
        time = convert_to_seconds(time, measurement.unit)
    flops = flop_count.get_total_flops()
    performance = flops / time
    intensity = flops / byte_count
    ax.scatter(intensity, performance, label=label)
    return intensity


def update_min_max(value: Number, min_value: Optional[Number] = None,
                   max_value: Optional[Number] = None) -> Tuple[Number, Number]:
    """
    Updates the given min, max values with the given value. If the given min, max values are None, will use the given
    value instead

    :param value: The value
    :type value: Number
    :param min_value: The min value to update, defaults to None
    :type min_value: Optional[Number], optional
    :param max_value: The max value to update, defaults to None
    :type max_value: Optional[Number], optional
    :return: The updated min and max value (in this order in the tuple)
    :rtype: Tuple[Number, Number]
    """
    if min_value is None:
        min_value = value
    min_value = min(value, min_value)
    if max_value is None:
        max_value = value
    max_value = max(value, max_value)
    return (min_value, max_value)


def plot_roofline_cycles(run_data: MeasurementRun, roofline_data: Dict[str, Tuple[FlopCount, Number]],
                         hardware_data: Dict, ax: matplotlib.axis.Axis, points_only: bool = False):
    peak_performance = hardware_data['flop_per_second']['theoretical'] / hardware_data['graphics_clock']

    ax.set_xlabel("Operational Intensity")
    ax.set_ylabel("Performance [flop/cycle]")

    min_intensity = None
    max_intensity = None
    for program_measurement in run_data.data:
        program = program_measurement.program
        label = f"{program} using {run_data.description}"
        for measurement in program_measurement.measurements['Kernel Cycles']:
            min_intensity, max_intensity = update_min_max(
                    draw_program_points(measurement, label, ax, *roofline_data[program]), min_intensity,
                    max_intensity)

    if not points_only:
        # Draw rooflines
        # Need to divide by the graphics clock to get the bytes/cycle in graphics cycles
        draw_roofline(ax, peak_performance,
                      hardware_data['bytes_per_second']['global']['measured'] / hardware_data['graphics_clock'],
                      'bytes / cycle',
                      min_intensity, max_intensity, color='black',
                      bandwidth_label="Global, Measured")
        # Using here the higher max graphics clock. Don't quite know if this is correct
        draw_roofline(ax, peak_performance,
                      hardware_data['bytes_per_second']['shared']['measured'] / hardware_data['graphics_clock'],
                      'bytes / cycle',
                      min_intensity, max_intensity, color='black',
                      bandwidth_label="Shared, Measured")
        draw_roofline(ax, peak_performance,
                      hardware_data['bytes_per_second']['l2']['measured'] / hardware_data['graphics_clock'],
                      'bytes / cylce',
                      min_intensity, max_intensity, color='black',
                      bandwidth_label="L2, Measured")
        draw_roofline(ax, peak_performance,
                      hardware_data['bytes_per_cycle']['l1']['measured'],
                      'bytes / cylce',
                      min_intensity, max_intensity, color='black',
                      bandwidth_label="L1, Measured")
    ax.legend()
    ax.grid()


def plot_roofline_seconds(run_data: MeasurementRun, roofline_data: Dict[str, Tuple[FlopCount, Number]],
                          hardware_data: Dict, ax: matplotlib.axis.Axis, points_only: bool = False):
    peak_performance = hardware_data['flop_per_second']['theoretical']

    ax.set_xlabel("Operational Intensity")
    ax.set_ylabel("Performance [flop/seconds]")

    min_intensity = None
    max_intensity = None
    for program_measurement in run_data.data:
        program = program_measurement.program
        label = f"{program} using {run_data.description}"
        for measurement in program_measurement.measurements['Kernel Time']:
            min_intensity, max_intensity = update_min_max(
                    draw_program_points(measurement, label, ax, *roofline_data[program]), min_intensity,
                    max_intensity)

    if not points_only:
        # Draw rooflines
        draw_roofline(ax, peak_performance,
                      hardware_data['bytes_per_second']['global']['measured'],
                      'bytes / second',
                      min_intensity, max_intensity, color='black',
                      bandwidth_label="Global, Measured")
        # Using here the higher max graphics clock. Don't quite know if this is correct
        draw_roofline(ax, peak_performance,
                      hardware_data['bytes_per_second']['shared']['measured'],
                      'bytes / second',
                      min_intensity, max_intensity, color='black',
                      bandwidth_label="Shared, Measured")
        draw_roofline(ax, peak_performance,
                      hardware_data['bytes_per_second']['l2']['measured'],
                      'bytes / second',
                      min_intensity, max_intensity, color='black',
                      bandwidth_label="L2, Measured")
        draw_roofline(ax, peak_performance,
                      hardware_data['bytes_per_cycle']['l1']['measured'] * hardware_data['graphics_clock'],
                      'bytes / second',
                      min_intensity, max_intensity, color='black',
                      bandwidth_label="L1, Measured")
    ax.legend()
    ax.grid()


def main():
    parser = ArgumentParser(description="Creates a roofline plot")
    parser.add_argument(
            'files',
            type=str,
            nargs='+',
            help='Basename of the results and roofline file. Without file ending')
    parser.add_argument(
            '--output',
            type=str,
            help='Name of the file where to store the plot without ending')

    args = parser.parse_args()

    plt.rcParams.update({'figure.figsize': (19, 10)})
    plt.rcParams.update({'font.size': 12})
    hardware_filename = 'nodes.json'

    figure = plt.figure()
    ax_cycles = figure.add_subplot(2, 1, 1)
    ax_seconds = figure.add_subplot(2, 1, 2)
    for index, file in enumerate(args.files):
        print(file)
        results_filename = path.join(get_results_dir(), f"{file}.json")
        roofline_filename = path.join(get_results_dir(), f"{file}_roofline.json")
        with open(results_filename) as results_file:
            with open(hardware_filename) as node_file:
                run_data = json.load(results_file, object_hook=MeasurementRun.from_json)
                roofline_data = read_roofline_data(roofline_filename)
                node_data = json.load(node_file)
                gpu = node_data['ault_nodes'][run_data.node]['GPU']
                figure.suptitle(f"Roofline on {run_data.node} using a {gpu}")
                plot_roofline_cycles(run_data, roofline_data, node_data['GPUs'][gpu], ax_cycles, points_only=index > 0)
                plot_roofline_seconds(run_data, roofline_data, node_data['GPUs'][gpu], ax_seconds,
                                      points_only=index > 0)

    if args.output is None:
        plot_filename = f"{args.files[0]}_roofline.pdf"
    else:
        plot_filename = f"{args.output}.pdf"
    print(f"Save plot into {plot_filename}")
    plt.savefig(plot_filename)


if __name__ == '__main__':
    main()
