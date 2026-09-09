"""Readable, display-only companions to saved LLM request samples."""

import json
import re
from html import escape

from markdown_it import MarkdownIt


MARKDOWN = MarkdownIt('commonmark', {'html': False})


def json_sections(text):
    """Yield prose and complete JSON objects/arrays without changing the source."""
    decoder = json.JSONDecoder()
    start = cursor = 0
    while cursor < len(text):
        if text[cursor] not in '{[':
            cursor += 1
            continue
        try:
            value, length = decoder.raw_decode(text[cursor:])
        except ValueError:
            cursor += 1
            continue
        if cursor > start:
            yield text[start:cursor], None
        yield text[cursor:cursor + length], value
        cursor += length
        start = cursor
    if start < len(text):
        yield text[start:], None


def literal(text):
    """Escape Markdown punctuation so saved text cannot create links or markup."""
    return re.sub(r'([\\`*_{}\[\]()#+.!|<>~-])', r'\\\1', str(text))


def unpack(value):
    """Represent every field in order, including empty and missing values."""
    if isinstance(value, (dict, list)):
        if not value:
            return 'Empty object' if isinstance(value, dict) else 'Empty list'
        items = value.items() if isinstance(value, dict) else enumerate(value, 1)
        lines = []
        for key, child in items:
            label = str(key).replace('_', ' ') if isinstance(value, dict) else f'Item {key}'
            text = unpack(child)
            if isinstance(child, (dict, list)) and child or '\n' in text:
                nested = '\n'.join('  ' + line if line else '' for line in text.split('\n'))
                lines.append(f'- **{literal(label)}:**\n\n{nested}')
            else:
                lines.append(f'- **{literal(label)}:** {text}')
        return '\n'.join(lines)
    if isinstance(value, str):
        parts = list(json_sections(value))
        if any(data is not None for _, data in parts):
            return '\n\n'.join(
                unpack(data) if data is not None else literal(source.strip())
                for source, data in parts)
        return literal(value) if value else 'Empty string'
    if value is None:
        return 'Not provided (null)'
    if isinstance(value, bool):
        return 'Yes (true)' if value else 'No (false)'
    return str(value)


def markdown_companion(value):
    return ('<section class="readable-sample" aria-label="Readable Markdown">'
            '<h4>Readable Markdown</h4>' + MARKDOWN.render(unpack(value)) + '</section>')


def message_samples(text):
    """Put a readable companion immediately after each embedded JSON sample."""
    content = ''
    for source, value in json_sections(text):
        content += '<pre class="message">' + escape(source) + '</pre>'
        if value is not None:
            content += markdown_companion(value)
    return content
