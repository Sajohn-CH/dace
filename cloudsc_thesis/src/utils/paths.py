from typing import List, Optional
from os.path import join, dirname, split, abspath, exists
from os import getcwd, listdir, makedirs


def create_if_not_exist(path: str) -> str:
    """
    Creates the folders in the given path and returns the path itself.

    :param path: The path
    :type path: str
    :return: The given path
    :rtype: str
    """
    if not exists(path):
        makedirs(path)
    return path


def get_dacecache() -> str:
    """
    Returns path to the currently used dacecache folder

    :return: The path to the .dacecache folder
    :rtype: str
    """
    return join(getcwd(), '.dacecache')


def get_default_sdfg_file(program: str) -> str:
    """
    Returns the path to the (default) sdfg file of the given program stored in the current .dacecache folder.
    Assumes that it has been generated before.

    :param program: The name of the program
    :type program: str
    :return: The path to the sdfg file
    :rtype: str
    """
    from utils.general import get_programs_data
    programs_data = get_programs_data()
    return join(get_dacecache(), f"{programs_data['programs'][program]}_routine", "program.sdfg")


def get_thesis_playground_root_dir() -> str:
    """
    Returns path to the thesis_playground folder in the dace repo. Should serve as root folder for most other paths

    :return: absoulte path to folder
    :rtype: str
    """
    return split(split(dirname(abspath(__file__)))[0])[0]


def get_verbose_graphs_dir() -> str:
    """
    Gets path to the directory where all the SDFGs are stored when SDGFs are generated verbosly (e.g. not for compiling)

    :return: Path to the dir
    :rtype: str
    """
    return join(get_thesis_playground_root_dir(), 'sdfg_graphs')


def get_sdfg_gen_code_folder() -> str:
    return create_if_not_exist(join(get_thesis_playground_root_dir(), 'sdfg_gen_code'))


def get_basic_sdfg_dir() -> str:
    return create_if_not_exist(join(get_thesis_playground_root_dir(), 'basic_sdfgs'))


def get_full_cloudsc_log_dir() -> str:
    return create_if_not_exist(join(get_thesis_playground_root_dir(), 'full_cloudsc_logs'))


def get_full_cloudsc_results_dir(node: Optional[str] = None, exp_id: Optional[int] = None) -> str:
    if node is not None:
        if exp_id is not None:
            return create_if_not_exist(join(get_full_cloudsc_log_dir(), 'results', node, str(exp_id)))
        return create_if_not_exist(join(get_full_cloudsc_log_dir(), 'results', node))
    return create_if_not_exist(join(get_full_cloudsc_log_dir(), 'results'))


def get_full_cloudsc_plot_dir(node: Optional[str] = None) -> str:
    if node is not None:
        return create_if_not_exist(join(get_full_cloudsc_log_dir(), 'plots', node))
    return create_if_not_exist(join(get_full_cloudsc_log_dir(), 'plots'))
