from typing import Dict, Union, Tuple
from numbers import Number
import numpy as np
import copy
import json


class FlopCount:
    adds: int
    muls: int
    divs: int
    minmax: int
    abs: int

    def __init__(self, adds: int = 0, muls: int = 0, divs: int = 0, minmax: int = 0, abs: int = 0, powers: int = 0,
                 roots: int = 0):
        self.adds = adds
        self.muls = muls
        self.divs = divs
        self.minmax = minmax
        self.abs = abs
        self.powers = powers
        self.roots = roots

    def get_total_flops(self) -> int:
        return self.adds + self.muls + 15*self.divs + 13*self.roots + 117*self.powers

    def __mul__(self, a: Number):
        return FlopCount(
            adds=self.adds * a,
            muls=self.muls * a,
            divs=self.divs * a,
            minmax=self.minmax * a,
            abs=self.abs * a,
            powers=self.powers * a,
            roots=self.roots * a)

    def __rmul__(self, a: Number):
        return self * a

    def __add__(self, other: 'FlopCount'):
        if not isinstance(other, type(self)):
            raise NotImplementedError
        else:
            return FlopCount(
                adds=self.adds + other.adds,
                muls=self.muls + other.muls,
                divs=self.divs + other.divs,
                minmax=self.minmax + other.minmax,
                abs=self.abs + other.abs,
                powers=self.powers + other.powers,
                roots=self.roots + other.roots)

    def to_dict(self) -> Dict[str, Number]:
        return {"adds": self.adds, "muls": self.muls, "divs": self.divs, "minmax": self.minmax, "abs": self.abs,
                "powers": self.powers, "roots": self.roots}


def save_roofline_data(data: Dict[str, Tuple[FlopCount, Number]], filename: str):
    all_dict = copy.deepcopy(data)
    for program in all_dict:
        all_dict[program] = (all_dict[program][0].to_dict(), all_dict[program][1])

    with open(filename, 'w') as file:
        print(f"Write file into {filename}")
        json.dump(all_dict, file)


def read_roofline_data(filename: str) -> Dict[str, Tuple[FlopCount, Number]]:
    with open(filename, 'r') as file:
        all_dict = json.load(file)
        for program in all_dict:
            all_dict[program] = (FlopCount(**all_dict[program][0]), all_dict[program][1])
        return all_dict


def get_number_of_flops(
        params: Dict[str, Number],
        inputs: Dict[str, Union[Number, np.ndarray]],
        outputs: Dict[str, Union[Number, np.ndarray]],
        program: str) -> FlopCount:
    KLEV = params['KLEV']
    NCLDTOP = params['NCLDTOP']
    KIDIA = params['KIDIA']
    KFDIA = params['KFDIA']
    if program == 'cloudsc_class1_658':
        return KLEV * (KFDIA-KIDIA+1) * FlopCount(adds=5, muls=5)
    elif program == 'cloudsc_class1_670':
        return (params['NCLV']-1) * KLEV * (KFDIA-KIDIA+1) * FlopCount(adds=2, muls=2)
    elif program == 'cloudsc_class1_2783':
        return (KLEV+1) * (KFDIA-KIDIA+1) * FlopCount(adds=2)
    elif program == 'cloudsc_class1_2857':
        return (KLEV+1) * (KFDIA-KIDIA+1) * FlopCount(adds=2, muls=2)
    elif program == 'cloudsc_class2_781':
        number_formula = np.count_nonzero(outputs['ZA'][KIDIA-1:KFDIA, NCLDTOP-1:KLEV] > inputs['RLMIN'])
        return number_formula * FlopCount(adds=1, divs=1) + KLEV * (KFDIA-KIDIA+1) * FlopCount(adds=1, minmax=2)
    elif program == 'cloudsc_class2_1516':
        number_formula_1 = np.count_nonzero(
                (inputs['ZA'][KIDIA-1:KFDIA, NCLDTOP-2:KLEV-1] < inputs['RCLDTOPCF']) &
                (inputs['ZA'][KIDIA-1:KFDIA, NCLDTOP-1:KLEV] >= inputs['RCLDTOPCF']))
        number_formula_2 = np.count_nonzero(
                (inputs['ZTP1'][KIDIA-1:KFDIA, NCLDTOP-1:KLEV] < inputs['RTT']) &
                (outputs['ZQXFG2'][KIDIA-1:KFDIA, NCLDTOP-1:KLEV, params['NCLDQL']] > inputs['RLMIN']))
        return number_formula_1 * FlopCount(adds=1, divs=1, muls=1) + \
            number_formula_2 * FlopCount(adds=17, muls=22, divs=11, powers=3, minmax=3)
    elif program == 'cloudsc_class2_1762':
        number_formula = np.count_nonzero(inputs['ZQPRETOT2'][KIDIA-1:KFDIA, NCLDTOP-1:KLEV] > inputs['ZEPSEC'])
        return number_formula * FlopCount(adds=4, muls=1, divs=3, minmax=5)
    elif program == 'cloudsc_class3_691':
        zqx_ql_qi = outputs['ZQX'][KIDIA-1:KFDIA, 0:KLEV, params['NCLDQI']] + \
                    outputs['ZQX'][KIDIA-1:KFDIA, 0:KLEV, params['NCLDQL']]
        number_iterations = np.count_nonzero(
                (zqx_ql_qi < inputs['RLMIN']) | (outputs['ZA'][KIDIA-1:KFDIA, 0:KLEV] < inputs['RAMIN']))
        # print(f"{number_iterations:,} / {(KLEV) * (KFDIA-KIDIA+1):,}")
        return number_iterations * FlopCount(adds=8, muls=4)
    elif program == 'cloudsc_class3_965':
        number_of_iterations = np.count_nonzero(
                inputs['ZQX'][KIDIA-1:KFDIA, NCLDTOP-1:KLEV, params['NCLDQL']] < inputs['RLMIN'])
        number_of_iterations += np.count_nonzero(
                inputs['ZQX'][KIDIA-1:KFDIA, NCLDTOP-1:KLEV, params['NCLDQI']] < inputs['RLMIN'])
        # print(f"{number_of_iterations:,} / {2 * (KLEV-NCLDTOP+1) * (KFDIA-KIDIA+1):,}")
        return number_of_iterations * FlopCount(adds=1)
    elif program == 'cloudsc_class3_1985':
        number_if_iterations = np.count_nonzero(
                (outputs['ZICETOT2'][KIDIA-1:KFDIA, NCLDTOP-1:KLEV] > inputs['ZEPSEC']) &
                (inputs['ZTP1'][KIDIA-1:KFDIA, NCLDTOP-1:KLEV] > inputs['RTT']))
        # print(f"{number_if_iterations:,} / {(KLEV-NCLDTOP+1) * (KFDIA-KIDIA+1):,}")
        return (KLEV-NCLDTOP+1) * (KFDIA-KIDIA+1) * FlopCount(adds=1) + \
            number_if_iterations * FlopCount(adds=8, muls=7, divs=1, minmax=2, abs=1)
    elif program == 'cloudsc_class3_2120':
        zqe = (inputs['ZQX'][KIDIA-1:KFDIA, NCLDTOP-1:KLEV, params['NCLDQV']]
               - inputs['ZA'][KIDIA-1:KFDIA, NCLDTOP-1:KLEV]) \
                        * np.maximum(inputs['ZEPSEC'], 1.0 - inputs['ZA'][KIDIA-1:KFDIA, NCLDTOP-1:KLEV])
        zqe = np.maximum(0.0, np.minimum(zqe, inputs['ZQSLIQ'][KIDIA-1:KFDIA, NCLDTOP-1:KLEV]))
        zzrh = np.maximum(inputs['ZEPSEC'], 1.0 - inputs['ZA'][KIDIA-1:KFDIA, NCLDTOP-1:KLEV])
        zzrh = inputs['ZCOVPMAX'][KIDIA-1:KFDIA] / zzrh.transpose()
        zzrh = inputs['RPRECRHMAX'] + (1.0 - inputs['RPRECRHMAX']) * zzrh.transpose()
        zzrh = np.minimum(zzrh, np.maximum(inputs['RPRECRHMAX'], 1.0))
        number_if_iterations = np.count_nonzero(
                (inputs['ZCOVPCLR'][KIDIA-1:KFDIA] > inputs['ZEPSEC']) &
                (outputs['ZQXFG2'][KIDIA-1:KFDIA, NCLDTOP-1:KLEV, params['NCLDQR']] > inputs['ZEPSEC']).transpose() &
                (zqe < zzrh * inputs['ZQSLIQ'][KIDIA-1:KFDIA, NCLDTOP-1:KLEV]).transpose())
        # print(f"{number_if_iterations:,} / {(KLEV-NCLDTOP+1) * (KFDIA-KIDIA+1):,}")
        return (KLEV-NCLDTOP+1) * (KFDIA-KIDIA+1) * FlopCount(adds=5, muls=2, divs=2, minmax=6) + \
            number_if_iterations * FlopCount(adds=8, muls=15, divs=6, minmax=5, abs=1, powers=1, roots=1)
    elif program == 'my_roofline_test':
        return KLEV * (KFDIA-KIDIA+1) * FlopCount(adds=1, roots=1)
    else:
        print(f"ERROR: No flop count available for program {program}")
        return None


# Length of a double in bytes
BYTES_DOUBLE = 8


def get_number_of_bytes_rough(
        params: Dict[str, Number],
        inputs: Dict[str, Union[Number, np.ndarray]],
        outputs: Dict[str, Union[Number, np.ndarray]],
        program: str) -> Number:
    """
    Very rough calculation of bytes transfered/used. Does not take real iteration ranges into account. Counts output
    arrays twice (copy in and copyout) and input only as once

    :param params: The parameters used for the given program
    :type params: Dict[str, Number]
    :param inputs: The inputs used for the given program
    :type inputs: Dict[str, Union[Number, np.ndarray]]
    :param outputs: The outputs used for the given program
    :type outputs: Dict[str, Union[Number, np.ndarray]]
    :param program: The program name
    :type program: str
    :return: Number of bytes
    :rtype: Number
    """
    bytes = BYTES_DOUBLE * (len(params) +
                            sum([np.prod(array.shape) if isinstance(array, np.ndarray) else 1 for array in inputs.values()]) +
                            sum([np.prod(array.shape) for array in outputs.values()]) * 2)
    return int(bytes)


def get_double_accessed(params: Dict[str, Number], program: str, variable: str) -> Number:
    """
    Get the number doubles access (read & writes) for the given variable in the given program

    :param params: The parameters used for the given program
    :type params: Dict[str, Number]
    :param program: The name of the program
    :type program: str
    :param variable: The name of the variable accessed
    :type variable: str
    :return: The number of doubles accessed
    :rtype: Number
    """
    KLEV = params['KLEV']
    NCLDTOP = params['NCLDTOP']
    KIDIA = params['KIDIA']
    KFDIA = params['KFDIA']
    iteration_shapes = {
        'cloudsc_class1_658': [
            {
                'variables': ['tendency_tmp_t', 'tendency_tmp_q', 'tendency_tmp_a', 'PT', 'PQ', 'PA'],
                'size': KLEV*(KFDIA-KIDIA+1),
                'action': 'r'
            },
            {
                'variables': ['ZTP1', 'ZQX', 'ZQX0', 'ZA', 'ZAORIG'],
                'size': KLEV*(KFDIA-KIDIA+1),
                'action': 'w'
            }
        ],
        'cloudsc_class1_670':
        [
            {'variables': ['ZQX', 'ZQX0'], 'size': (params['NCLV']-1)*(KLEV)*(KFDIA-KIDIA+1), 'action': 'w'},
            {
                'variables': ['PCLV', 'tendency_tmp_cld'],
                'size': (params['NCLV']-1)*(KLEV)*(KFDIA-KIDIA+1),
                'action': 'r'
            },

        ],
        'cloudsc_class1_2783':
        [
            {'variables': ['ZPFPLSX'], 'size': 4*(KLEV+1)*(KFDIA-KIDIA+1), 'action': 'r'},
            {'variables': ['PFPLSL', 'PFPLSN'], 'size': (KLEV+1)*(KFDIA-KIDIA+1), 'action': 'w'},

        ],
        'cloudsc_class1_2857':
        [
            {'variables': ['PFPLSL', 'PFPLSN'], 'size': (KLEV+1)*(KFDIA-KIDIA+1), 'action': 'r'},
            {'variables': ['PFHPSL', 'PFHPSN'], 'size': (KLEV+1)*(KFDIA-KIDIA+1), 'action': 'w'},

        ],
        'cloudsc_class2_781':
        [
            {'variables': ['ZQX'], 'size': 2*(KLEV)*(KFDIA-KIDIA+1), 'action': 'r'},
            {'variables': ['ZA', 'ZLI'], 'size': (KLEV)*(KFDIA-KIDIA+1), 'action': 'r'},
            {'variables': ['ZLIQFRAC', 'ZICEFRAC'], 'size': (KLEV)*(KFDIA-KIDIA+1), 'action': 'w'},

        ],
        'cloudsc_class2_1516':
        [
            {'variables': ['ZA'], 'size': (KLEV-NCLDTOP+1)*(KFDIA-KIDIA+2), 'action': 'r'},
            # Technically, it is only w for one branch
            {'variables': ['ZCLDTOPDIST2'], 'size': 2*(KLEV-NCLDTOP+1)*(KFDIA-KIDIA+1), 'action': 'rw'},
            {'variables': ['ZDP', 'ZRHO', 'ZFOKOOP', 'ZICECLD'], 'size': (KFDIA-KIDIA+1), 'action': 'r'},
            {'variables': ['ZTP1', 'PAP'], 'size': (KLEV-NCLDTOP+1)*(KFDIA-KIDIA+1), 'action': 'r'},
            {'variables': ['ZSOLQA2', 'ZQXFG2'], 'size': 2*2*(KLEV-NCLDTOP+1)*(KFDIA-KIDIA+1), 'action': 'rw'},

        ],
        'cloudsc_class2_1762':
        [
            {'variables': ['ZQXFG'], 'size': 2*(KFDIA-KIDIA+1), 'action': 'r'},
            {'variables': ['ZA'], 'size': (KLEV)*(KFDIA-KIDIA+2), 'action': 'r'},
            {'variables': ['ZQPRETOT2'], 'size': (KLEV)*(KFDIA-KIDIA+1), 'action': 'r'},
            {'variables': ['ZCOVPTOT2', 'ZCOVPMAX2'], 'size': 2*(KLEV)*(KFDIA-KIDIA+1), 'action': 'rw'},
            {'variables': ['ZCOVPCLR2', 'ZRAINCLD2', 'ZSNOWCLD2'], 'size': (KLEV)*(KFDIA-KIDIA+1), 'action': 'w'},

        ],
        'cloudsc_class3_691':
        [
            {'variables': ['tendency_loc_q', 'tendency_loc_T', 'ZA'], 'size': 2*(KLEV-NCLDTOP+1)*(KFDIA-KIDIA+1), },
            {'variables': ['ZQX'], 'size': 6*(KLEV-NCLDTOP+1)*(KFDIA-KIDIA+1), },
            {'variables': ['ZLNEG'], 'size': 4*(KLEV-NCLDTOP+1)*(KFDIA-KIDIA+1), }
        ],
        'cloudsc_class3_965':
        [
            {'variables': ['ZSOLQA2'], 'size': 4*(KLEV-NCLDTOP+1)*(KFDIA-KIDIA+1), },
            {'variables': ['ZQX'], 'size': 2*(KLEV-NCLDTOP+1)*(KFDIA-KIDIA+1), },
        ],
        'cloudsc_class3_1985':
        [
            {
                'variables': ['PAP', 'ZTP1', 'ZQSICE', 'ZICETOT2', 'ZMELTMAX2'],
                'size': 1*(KLEV-NCLDTOP+1)*(KFDIA-KIDIA+1),
            },
            {'variables': ['ZQXFG'], 'size': 2*(KFDIA-KIDIA+1), },
            {'variables': ['ZQX'], 'size': 1*(KLEV-NCLDTOP+1)*(KFDIA-KIDIA+1), }
        ],
        'cloudsc_class3_2120':
        [
            {'variables': ['ZA', 'ZQSLIQ', 'PAP'], 'size': 1*(KLEV-NCLDTOP+1)*(KFDIA-KIDIA+1), },
            {'variables': ['ZQX'], 'size': 1*(KLEV-NCLDTOP+1)*(KFDIA-KIDIA+1), },
            {'variables': ['ZCOVPCLR', 'ZDTGDP', 'ZCORQSLIQ', 'ZCOVPMAX', 'ZDP'], 'size': 1*(KFDIA-KIDIA+1), },
            {'variables': ['PAPH'], 'size': 1*(KLEV-NCLDTOP+1), },
            {'variables': ['ZSOLQA2'], 'size': 4*(KLEV-NCLDTOP+1)*(KFDIA-KIDIA+1), },
            {'variables': ['ZCOVPTOT2', 'ZQXFG2'], 'size': 2*(KLEV-NCLDTOP+1)*(KFDIA-KIDIA+1), },
        ],
        'my_roofline_test':
        [
            {'variables': ['ARRAY_A', 'ARRAY_B', 'ARRAY_C'], 'size': (KLEV)*(KFDIA-KIDIA+1), },
        ],
    }

    for entry in iteration_shapes[program]:
        # print(program, variable, entry['variables'], variable in entry['variables'])
        if variable in entry['variables']:
            return entry['size']
    print(f"ERROR: could not find iteration shape for variable {variable} in program {program}")
    return None


def get_number_of_bytes(
        params: Dict[str, Number],
        inputs: Dict[str, Union[Number, np.ndarray]],
        outputs: Dict[str, Union[Number, np.ndarray]],
        program: str) -> Number:
    """
    Less rough calculation of bytes transfered/used. Does not take real iteration ranges into account. Counts output
    arrays twice (copy in and copyout) and input only as once

    :param params: The parameters used for the given program
    :type params: Dict[str, Number]
    :param inputs: The inputs used for the given program
    :type inputs: Dict[str, Union[Number, np.ndarray]]
    :param outputs: The outputs used for the given program
    :type outputs: Dict[str, Union[Number, np.ndarray]]
    :param program: The program name
    :type program: str
    :return: Number of bytes
    :rtype: Number
    """

    bytes = BYTES_DOUBLE * len(params)
    for input in inputs:
        if isinstance(inputs[input], np.ndarray):
            bytes += BYTES_DOUBLE * get_double_accessed(params, program, input)
            # print(f"{input}: rough: {np.prod(inputs[input].shape):,}, "
            #       f"precise: {get_double_accessed(params, program, input):,}")
        else:
            bytes += BYTES_DOUBLE
    for output in outputs:
        bytes += BYTES_DOUBLE * get_double_accessed(params, program, output)
        # print(f"{output}: rough: {np.prod(outputs[output].shape)*2:,}, "
        #       f"precise: {get_double_accessed(params, program, output):,}")

    return int(bytes)
