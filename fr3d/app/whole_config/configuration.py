"""Schema-backed defaults, parameter metadata, and candidate validation."""

from copy import deepcopy
from itertools import product
import json
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

from .value_space import finite_values
from .validation import submission_schema


EPSILON_PAIR = 'epsilon_pair'
EPSILON_PATHS = ('epsilon.initial', 'epsilon.decay')
REWARD_PAIR = 'reward_pair'
REWARD_PATHS = ('game.rewards.closer_to_food', 'game.rewards.further_from_food')
PAIR_PATHS = {EPSILON_PAIR: EPSILON_PATHS, REWARD_PAIR: REWARD_PATHS}


SCHEMA_PATH = Path(__file__).resolve().parents[3] / 'pages/snake-lab-schemas/simulation-config-v2.schema.json'
FIXED = {
    'seed': 1970, 'epochs': 1500, 'game.board_width': 20,
    'game.board_height': 20, 'game.initial_snake_length': 3,
}


def leaves(schema, prefix=''):
    for name, child in schema['properties'].items():
        path = f'{prefix}.{name}' if prefix else name
        if child['type'] == 'object':
            yield from leaves(child, path)
        else:
            yield path, child


def get_value(config, path):
    for key in path.split('.'):
        config = config[key]
    return config


def set_value(config, path, value):
    *parents, key = path.split('.')
    for parent in parents:
        config = config.setdefault(parent, {})
    config[key] = value


class Configuration:
    def __init__(self, path=SCHEMA_PATH):
        self.schema = json.loads(Path(path).read_text(encoding='utf-8'))
        Draft202012Validator.check_schema(self.schema)
        self.validator = Draft202012Validator(submission_schema(self.schema))
        self.fields = dict(leaves(self.schema))
        paired_paths = {path for paths in PAIR_PATHS.values() for path in paths}
        self.parameters = {path: field for path, field in self.fields.items()
                           if path not in FIXED and path not in paired_paths and 'const' not in field}
        self.pair_values = {}
        for parameter, paths in PAIR_PATHS.items():
            self.pair_values[parameter] = {}
            for path in paths:
                field = self.fields[path]
                continuous = (field['type'] == 'number'
                              and not any(key in field for key in ('enum', 'const', 'multipleOf'))
                              and any(key in field for key in ('minimum', 'exclusiveMinimum'))
                              and any(key in field for key in ('maximum', 'exclusiveMaximum')))
                try:
                    self.pair_values[parameter][path] = None if continuous else finite_values(field)
                except ValueError as error:
                    raise ValueError(f'{path}: {error}') from error
            self.parameters[parameter] = {
                'type': 'object',
                'properties': {path.split('.')[-1]: self.fields[path] for path in paths},
                'required': [path.split('.')[-1] for path in paths], 'additionalProperties': False,
            }

    def paths(self, parameter):
        if parameter not in self.parameters:
            raise ValueError(f'Parameter is not searchable: {parameter}')
        return PAIR_PATHS.get(parameter, (parameter,))

    def value(self, config, parameter):
        values = tuple(get_value(config, path) for path in self.paths(parameter))
        return values if parameter in PAIR_PATHS else values[0]

    def pair_arguments(self, parameter, values):
        return dict(zip(self.parameters[parameter]['required'], values, strict=True))

    def legal_pairs(self, baseline, parameter=EPSILON_PAIR):
        """Return the planned grid; server acceptance is checked on submission."""
        axes = [self.pair_values[parameter][path] for path in self.paths(parameter)]
        return None if any(axis is None for axis in axes) else tuple(product(*axes))

    def validate_changes(self, baseline, config, parameter):
        self.validate(config)
        changed = {path for path in self.fields if get_value(config, path) != get_value(baseline, path)}
        allowed = set(self.paths(parameter))
        if not changed or not changed <= allowed:
            raise ValueError('The proposal must change exactly the selected parameter or pair')
        return config

    def validate(self, config):
        try:
            # JSON Schema numbers must also be representable as finite JSON numbers.
            json.dumps(config, allow_nan=False)
            self.validator.validate(config)
        except (ValidationError, TypeError, ValueError) as error:
            raise ValueError(str(error)) from error
        fixed = {path: field['const'] for path, field in self.fields.items() if 'const' in field}
        fixed.update(FIXED)
        for path, value in fixed.items():
            if get_value(config, path) != value:
                raise ValueError(f'{path} must remain {value}')
        return config

    def baseline(self):
        config = {}
        for path, field in self.fields.items():
            set_value(config, path, deepcopy(field['default']))
        for path, value in FIXED.items():
            set_value(config, path, value)
        return self.validate(config)

    def candidate(self, gold, parameter, arguments):
        self.paths(parameter)
        if parameter in PAIR_PATHS:
            required = self.parameters[parameter]['required']
            if not isinstance(arguments, dict) or set(arguments) != set(required):
                raise ValueError(f'Supply only {" and ".join(required)} together')
            config = deepcopy(gold)
            for path in self.paths(parameter):
                value = arguments[path.split('.')[-1]]
                if self.fields[path]['type'] == 'integer' and type(value) is float and value.is_integer():
                    value = int(value)
                set_value(config, path, value)
            return self.validate(config)
        if not isinstance(arguments, dict) or set(arguments) != {'value'}:
            raise ValueError('Supply only value')
        config = deepcopy(gold)
        value = arguments['value']
        # Normalize integral JSON numbers for Snake Lab's integer fields.
        if self.parameters[parameter]['type'] == 'integer' and type(value) is float and value.is_integer():
            value = int(value)
        set_value(config, parameter, value)
        # An unchanged value is valid but will be rejected as a duplicate.
        return self.validate(config)

    def tool(self, parameter):
        if parameter in PAIR_PATHS:
            return {'type': 'function', 'function': {
                'name': f'submit_{parameter}',
                'description': f'Propose {" and ".join(self.parameters[parameter]["required"])} together for the next experiment.',
                'parameters': submission_schema(self.parameters[parameter]),
            }}
        return {
            'type': 'function', 'function': {
                'name': 'submit_parameter',
                'description': f'Propose the next value for {parameter}.',
                'parameters': {
                    'type': 'object', 'properties': {'value': submission_schema(self.parameters[parameter])},
                    'required': ['value'], 'additionalProperties': False,
                },
            },
        }
