"""Schema-backed defaults, parameter metadata, and candidate validation."""

from copy import deepcopy
import json
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError


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
        self.parameters = {path: field for path, field in self.fields.items() if path not in FIXED}

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
        if parameter not in self.parameters:
            raise ValueError(f'Parameter is not searchable: {parameter}')
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
