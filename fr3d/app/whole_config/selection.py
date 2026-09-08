"""Choose the least explored eligible parameter relative to current gold."""

from fractions import Fraction
import math
import random

from .configuration import get_value


def exhausted(field, used):
    if 'enum' in field:
        return all(value in used for value in field['enum'])
    if field['type'] not in ('integer', 'number'):
        return False
    if field['type'] == 'number' and 'multipleOf' not in field:
        return False
    if not (('minimum' in field or 'exclusiveMinimum' in field)
            and ('maximum' in field or 'exclusiveMaximum' in field)):
        return False
    # Count legal multiples using exact decimal arithmetic, without enumerating
    # potentially large ranges. Integer multiples of p/q are multiples of p.
    step = Fraction(str(field.get('multipleOf', 1)))
    if field['type'] == 'integer':
        step = Fraction(step.numerator)
    lower = math.ceil(Fraction(str(field['minimum'])) / step) if 'minimum' in field else math.floor(
        Fraction(str(field['exclusiveMinimum'])) / step) + 1
    if 'exclusiveMinimum' in field:
        lower = max(lower, math.floor(Fraction(str(field['exclusiveMinimum'])) / step) + 1)
    upper = math.floor(Fraction(str(field['maximum'])) / step) if 'maximum' in field else math.ceil(
        Fraction(str(field['exclusiveMaximum'])) / step) - 1
    if 'exclusiveMaximum' in field:
        upper = min(upper, math.ceil(Fraction(str(field['exclusiveMaximum'])) / step) - 1)
    indices = {Fraction(str(value)) / step for value in used}
    count = sum(index.denominator == 1 and lower <= index <= upper for index in indices)
    return count == max(0, upper - lower + 1)


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
