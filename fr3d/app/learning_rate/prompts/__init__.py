"""Each prompt owns its instructions and available tools."""

from dataclasses import dataclass
from pathlib import Path

from ..tools import SUBMIT_LR, EXPERIMENT_REPORT, SUMMARY_REPORT

DATA = Path(__file__).resolve().parent.parent / 'prompt_data'


@dataclass(frozen=True)
class Prompt:
    number: str
    text: str
    tools: tuple


def outline_challenge():
    return Prompt('01', (DATA / '01.md').read_text(), (EXPERIMENT_REPORT, SUBMIT_LR))


def value_already_used(learning_rate):
    return Prompt('02', (DATA / '02.md').read_text().format(learning_rate=learning_rate),
                  (SUMMARY_REPORT, SUBMIT_LR))
