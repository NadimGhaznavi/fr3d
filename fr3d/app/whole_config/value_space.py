"""Count legal schema values and unused choices without enumerating large ranges."""

from fractions import Fraction
import math

from jsonschema import Draft202012Validator

from .validation import submission_schema


def finite_values(field):
    """Enumerate a finite numeric field, using exact steps and local type/bounds checks."""
    if 'const' in field:
        values = [field['const']]
    elif 'enum' in field:
        values = field['enum']
    else:
        total, _ = availability(field, set())
        if total is None:
            raise ValueError('Paired fields require finite enumerable value sets')
        step = Fraction(str(field.get('multipleOf', 1)))
        if field['type'] == 'integer':
            step = Fraction(step.numerator)
        lower = math.ceil(Fraction(str(field['minimum'])) / step) if 'minimum' in field else math.floor(
            Fraction(str(field['exclusiveMinimum'])) / step) + 1
        if 'exclusiveMinimum' in field:
            lower = max(lower, math.floor(Fraction(str(field['exclusiveMinimum'])) / step) + 1)
        values = [int(index * step) if field['type'] == 'integer' else float(index * step)
                  for index in range(lower, lower + total)]
    validator = Draft202012Validator(submission_schema(field))
    return tuple(sorted({value for value in values if validator.is_valid(value)}))


def availability(field, used):
    if 'enum' in field:
        legal = set(field['enum'])
        return len(legal), len(legal - used)
    if field['type'] not in ('integer', 'number'):
        return None, None
    if field['type'] == 'number' and 'multipleOf' not in field:
        return None, None
    if not (('minimum' in field or 'exclusiveMinimum' in field)
            and ('maximum' in field or 'exclusiveMaximum' in field)):
        return None, None
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
    total = max(0, upper - lower + 1)
    return total, total - count


def exhausted(field, used):
    _, remaining = availability(field, used)
    return remaining == 0
