"""Schema-backed defaults, parameter metadata, and candidate validation."""

from copy import deepcopy
from itertools import product
import json
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

from .value_space import finite_values


EPSILON_PAIR = 'epsilon_pair'
EPSILON_PATHS = ('epsilon.initial', 'epsilon.decay')


SCHEMA_PATH = Path(__file__).resolve().parents[3] / 'pages/snake-lab-schemas/simulation-config-v1.schema.json'
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
        self.validator = Draft202012Validator(self.schema)
        self.fields = dict(leaves(self.schema))
        self.parameters = {path: field for path, field in self.fields.items()
                           if path not in FIXED and path not in EPSILON_PATHS and 'const' not in field}
        self.epsilon_values = {}
        for path in EPSILON_PATHS:
            try:
                self.epsilon_values[path] = finite_values(self.fields[path])
            except ValueError as error:
                raise ValueError(f'{path}: {error}') from error
        self.parameters[EPSILON_PAIR] = {
            'type': 'object',
            'properties': {path.split('.')[1]: self.fields[path] for path in EPSILON_PATHS},
            'required': ['initial', 'decay'], 'additionalProperties': False,
        }

    def paths(self, parameter):
        if parameter not in self.parameters:
            raise ValueError(f'Parameter is not searchable: {parameter}')
        return EPSILON_PATHS if parameter == EPSILON_PAIR else (parameter,)

    def value(self, config, parameter):
        values = tuple(get_value(config, path) for path in self.paths(parameter))
        return values if parameter == EPSILON_PAIR else values[0]

    def legal_pairs(self, baseline):
        """Filter the Cartesian product through complete-configuration validation."""
        pairs = []
        for initial, decay in product(*(self.epsilon_values[path] for path in EPSILON_PATHS)):
            try:
                self.candidate(baseline, EPSILON_PAIR, {'initial': initial, 'decay': decay})
            except ValueError:
                continue
            pairs.append((initial, decay))
        return tuple(pairs)

    def validate_changes(self, baseline, config, parameter):
        self.validate(config)
        changed = {path for path in self.fields if get_value(config, path) != get_value(baseline, path)}
        allowed = set(self.paths(parameter))
        if not changed or not changed <= allowed:
            raise ValueError('The proposal must change exactly the selected parameter or epsilon pair')
        return config

    def validate(self, config):
        try:
            # JSON Schema numbers must also be representable as finite JSON numbers.
            json.dumps(config, allow_nan=False)
            self.validator.validate(config)
        except (ValidationError, TypeError, ValueError) as error:
            raise ValueError(str(error)) from error
        for path, value in FIXED.items():
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
        if parameter == EPSILON_PAIR:
            if not isinstance(arguments, dict) or set(arguments) != {'initial', 'decay'}:
                raise ValueError('Supply only initial and decay together')
            config = deepcopy(gold)
            for path in EPSILON_PATHS:
                set_value(config, path, arguments[path.split('.')[1]])
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
        if parameter == EPSILON_PAIR:
            return {'type': 'function', 'function': {
                'name': 'submit_epsilon_pair',
                'description': 'Propose epsilon initial and decay together for the next experiment.',
                'parameters': self.parameters[parameter],
            }}
        return {
            'type': 'function', 'function': {
                'name': 'submit_parameter',
                'description': f'Propose the next value for {parameter}.',
                'parameters': {
                    'type': 'object', 'properties': {'value': self.parameters[parameter]},
                    'required': ['value'], 'additionalProperties': False,
                },
            },
        }
