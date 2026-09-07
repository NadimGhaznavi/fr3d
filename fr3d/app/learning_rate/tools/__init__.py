"""Tools exposed to each prompt; submission only proposes a value."""

import math


def tool(name, description, properties=None, required=None):
    return {'type': 'function', 'function': {
        'name': name, 'description': description,
        'parameters': {'type': 'object', 'properties': properties or {},
                       'required': required or [], 'additionalProperties': False},
    }}


SUBMIT_LR = tool(
    'submit_learning_rate', 'Submit the learning rate for the next experiment.',
    {'learning_rate': {'type': 'number', 'exclusiveMinimum': 0, 'maximum': 1}},
    ['learning_rate'],
)
EXPERIMENT_REPORT = tool(
    'view_experiment_report', 'View a completed experiment; omit the ID for the latest.',
    {'experiment_id': {'type': 'integer', 'minimum': 1}},
)
SUMMARY_REPORT = tool('view_experiments_summary_report', 'View learning rates and high scores for completed experiments.')


def validate_learning_rate(arguments):
    if not isinstance(arguments, dict) or set(arguments) != {'learning_rate'}:
        raise ValueError('Supply only learning_rate')
    rate = arguments['learning_rate']
    if type(rate) not in (int, float) or not math.isfinite(rate) or not 0 < rate <= 1:
        raise ValueError('learning_rate must be finite, greater than zero and at most one')
    return float(rate)


def view_report(name, arguments, reports):
    if not isinstance(arguments, dict):
        raise ValueError('Tool arguments must be an object')
    if name == 'view_experiment_report' and set(arguments) <= {'experiment_id'}:
        return reports.experiment(**arguments)
    if name == 'view_experiments_summary_report' and not arguments:
        return reports.summary()
    raise ValueError('Unknown report tool or invalid arguments')
