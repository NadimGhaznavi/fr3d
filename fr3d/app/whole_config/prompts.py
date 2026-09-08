"""Load conversation prompts and render schema-specific value instructions."""

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class Prompt:
    number: str
    text: str


def prompt(name):
    path = Path(__file__).with_name('prompt_data') / f'{name}.md'
    return Prompt(name, path.read_text(encoding='utf-8'))


def parameter_instructions(parameter, field):
    """Render the selected schema field as explicit value instructions."""
    numeric_type = 'an integer' if field['type'] == 'integer' else 'a number'
    lines = [f'Please choose a value for `{parameter}`. The value MUST be {numeric_type}.']
    if 'const' in field:
        lines.append(f"The value must equal {json.dumps(field['const'])}.")
    if 'enum' in field:
        lines.append('The value must be one of:')
        lines.extend(f'- {json.dumps(value)}' for value in field['enum'])
    for keyword, wording in (
        ('minimum', 'greater than or equal to'),
        ('maximum', 'less than or equal to'),
        ('exclusiveMinimum', 'greater than'),
        ('exclusiveMaximum', 'less than'),
    ):
        if keyword in field:
            lines.append(f'The value must be {wording} {json.dumps(field[keyword])}.')
    if 'multipleOf' in field:
        lines.append(f"The value must be divisible by {json.dumps(field['multipleOf'])}.")
    return '\n'.join(lines)
