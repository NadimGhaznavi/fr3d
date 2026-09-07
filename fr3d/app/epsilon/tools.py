"""The LLM proposes a decay; only the main loop launches experiments."""

import math

SUBMIT_EPSILON_DECAY = {
    'type': 'function',
    'function': {
        'name': 'submit_epsilon_decay',
        'description': 'Propose epsilon decay for the next experiment.',
        'parameters': {
            'type': 'object',
            'properties': {'epsilon_decay': {
                'type': 'number', 'exclusiveMinimum': 0, 'maximum': 1,
            }},
            'required': ['epsilon_decay'], 'additionalProperties': False,
        },
    },
}


def validate_epsilon_decay(arguments):
    if not isinstance(arguments, dict) or set(arguments) != {'epsilon_decay'}:
        raise ValueError('Supply only epsilon_decay')
    value = arguments['epsilon_decay']
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 1:
        raise ValueError('epsilon_decay must be finite, greater than zero and at most one')
    return float(value)
