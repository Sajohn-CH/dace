from typing import Dict, Optional
from numbers import Number
import copy
from argparse import Namespace
import json


parameters = {
    'KLON': 10000,
    'KLEV': 10000,
    'KIDIA': 2,
    'KFDIA': 9998,
    'NCLV': 10,
    'NCLDQI': 3,
    'NCLDQL': 4,
    'NCLDQR': 5,
    'NCLDQS': 6,
    'NCLDQV': 7,
    'NCLDTOP': 2,
    'NSSOPT': 1,
    'NPROMA': 1,
    'NBLOCKS': 10000,
}

# changes from the parameters dict for certrain programs
custom_parameters = {
    'cloudsc_class1_658': {
        'KLON': 5000,
        'KLEV': 5000,
        'KFDIA': 4998,
    },
    'cloudsc_class1_670': {
        'KLON': 1000,
        'KLEV': 1000,
        'KFDIA': 998,
    },
    'cloudsc_class2_781': {
        'KLON': 5000,
        'KLEV': 5000,
        'KFDIA': 4998
    },
    'my_test': {
        'KLON': 100000000
    },
    'cloudsc_class2_1516':
    {
        'KLON': 3000,
        'KLEV': 3000,
        'KFDIA': 2998
    },
    'cloudsc_class3_691': {
        'KLON': 3000,
        'KLEV': 3000,
        'KFDIA': 2998
    },
    'cloudsc_class3_965': {
        'KLON': 3000,
        'KLEV': 3000,
        'KFDIA': 2998
    },
    'cloudsc_class3_1985': {
        'KLON': 3000,
        'KLEV': 3000,
        'KFDIA': 2998
    },
    'cloudsc_class3_2120': {
        'KLON': 3000,
        'KLEV': 3000,
        'KFDIA': 2998
    },
    'my_roofline_test':
    {
        'KLON': 10000,
        'KLEV': 10000,
        'KIDIA': 1,
        'KFDIA': 10000,
    },
    'cloudsc_vert_loop_2':
    {
        'KLEV': 137,
        'KLON': 1,
        'NPROMA': 1,
        'NBLOCKS': 10000
    },
    'cloudsc_vert_loop_4':
    {
        'KLEV': 137,
        'KLON': 1,
        'KFDIA': 1,
        'KIDIA': 1,
        # 'NBLOCKS': 3000,
        'NBLOCKS': 20000
    },
    'cloudsc_vert_loop_5':
    {
        'KLEV': 137,
        'KLON': 1,
        'KFDIA': 1,
        'KIDIA': 1,
        'NBLOCKS': 200000
    }
}


# changes from the parameters dict for testing
testing_parameters = {'KLON': 10, 'KLEV': 10, 'KFDIA': 8, 'NBLOCKS': 10}


class ParametersProvider:
    parameters: Dict[str, Number]
    program: str

    def __init__(self, program: str, testing: bool = False, update: Optional[Dict[str, Number]] = None):
        self.program = program
        self.parameters = copy.deepcopy(parameters)
        self.parameters.update(custom_parameters[program])
        if update is not None:
            self.parameters.update(update)

    def update_from_args(self, args: Namespace):
        args_dict = vars(args)
        for key in args_dict:
            if key in self.parameters and args_dict[key] is not None:
                self.parameters[key] = args_dict[key]

    def __getitem__(self, key: str) -> Number:
        return self.parameters[key]

    def __len__(self) -> int:
        return len(self.parameters)

    def __str__(self) -> str:
        return ' '.join([f"{key}: {value}" for key, value in self.parameters.items()])

    @staticmethod
    def to_json(params: 'ParametersProvider') -> Dict:
        return copy.deepcopy(params.parameters).update({'__ParametersProvider__': True, 'program': params.program})

    @staticmethod
    def from_json(dict: Dict) -> 'ParametersProvider':
        if '__ParametersProvider__' in dict:
            del dict['__ParametersProvider__']
            params = ParametersProvider(dict['program'])
            del dict['program']
            params.parameters = dict
            return params
        else:
            return dict
