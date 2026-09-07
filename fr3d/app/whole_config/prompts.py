"""Load the four parameter-independent conversation prompts."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Prompt:
    number: str
    text: str


def prompt(name):
    path = Path(__file__).with_name('prompt_data') / f'{name}.md'
    return Prompt(name, path.read_text(encoding='utf-8'))
