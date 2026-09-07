"""Load the initial epsilon prompts from disk."""

from dataclasses import dataclass
from pathlib import Path

DATA = Path(__file__).resolve().parent / 'prompt_data'


@dataclass(frozen=True)
class Prompt:
    number: str
    text: str


def first_contact():
    return Prompt('first_contact', (DATA / 'first_contact.md').read_text())


def invalid_value():
    return Prompt('invalid_value', (DATA / 'invalid_value.md').read_text())
