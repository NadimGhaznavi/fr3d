"""Choose the least explored eligible parameter relative to current gold."""

import math
import random

from .configuration import get_value


def exhausted(field, used):
    if field['type'] != 'integer':
        return False
    lower = math.ceil(field['minimum']) if 'minimum' in field else math.floor(field['exclusiveMinimum']) + 1
    upper = math.floor(field['maximum']) if 'maximum' in field else math.ceil(field['exclusiveMaximum']) - 1
    return sum(lower <= value <= upper for value in used) == upper - lower + 1


def select_parameter(configuration, reports, gold, choose=random.choice):
    candidates = []
    for parameter, field in configuration.parameters.items():
        history = reports.history(gold, parameter)
        if exhausted(field, {row['value'] for row in history}):
            continue
        completed = [row for row in history if row['status'] == 'completed']
        if not any(row['run_id'] == gold['run_id'] for row in completed):
            raise ValueError('Gold is missing from matching configuration history')
        values = {row['value'] for row in completed}
        report = {
            'parameter': parameter, 'constraints': field,
            'gold': gold,
            'experiments': [{key: row[key] for key in ('run_id', 'value', 'high_score')} for row in completed],
        }
        first_contact = values == {get_value(gold['config'], parameter)}
        candidates.append((len(values), parameter, first_contact, report))
    if not candidates:
        return None
    minimum = min(item[0] for item in candidates)
    _, parameter, first_contact, report = choose([item for item in candidates if item[0] == minimum])
    return parameter, first_contact, report
