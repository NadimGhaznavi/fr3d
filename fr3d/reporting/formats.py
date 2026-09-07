"""A small, lossless JSON-to-Markdown mapping for report objects."""

import json


def to_json(data):
    return json.dumps(data, ensure_ascii=False, allow_nan=False)


def _label(key):
    return str(key).replace('_', ' ').capitalize().replace('Id', 'ID', 1)


def _cell(value):
    text = 'Not available' if value is None else (
        value if isinstance(value, str) else to_json(value)
    )
    for char in ('\\', '`', '*', '_', '[', ']', '<', '>', '|', '#'):
        text = text.replace(char, '\\' + char)
    return text.replace('\r', '').replace('\n', ' / ')


def to_markdown(data, title='Report'):
    # Validate the same data types and finite numbers as the JSON representation.
    to_json(data)
    lines = [f'# {_cell(title)}', '']

    def render(value, depth):
        if isinstance(value, dict):
            for key, item in value.items():
                if isinstance(item, (dict, list)):
                    lines.extend(['', '#' * min(depth, 6) + ' ' + _label(key), ''])
                    render(item, depth + 1)
                else:
                    lines.append(f'- **{_label(key)}:** {_cell(item)}')
        elif isinstance(value, list):
            if not value:
                lines.append('No records.')
            elif all(isinstance(row, dict) and all(not isinstance(v, (dict, list)) for v in row.values())
                     for row in value):
                keys = list(dict.fromkeys(key for row in value for key in row))
                lines.append('| ' + ' | '.join(_label(key) for key in keys) + ' |')
                lines.append('| ' + ' | '.join('---' for _ in keys) + ' |')
                lines.extend('| ' + ' | '.join(_cell(row.get(key)) for key in keys) + ' |' for row in value)
            else:
                for item in value:
                    render(item, depth)
                    lines.append('')
        else:
            lines.append(_cell(value))

    render(data, 2)
    return '\n'.join(lines) + '\n'
