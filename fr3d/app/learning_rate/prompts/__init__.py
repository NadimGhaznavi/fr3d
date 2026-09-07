"""Each prompt owns its instructions and available tools."""

from dataclasses import dataclass
from pathlib import Path

from ..tools import SUBMIT_LR, EXPERIMENT_REPORT

DATA = Path(__file__).resolve().parent.parent / 'prompt_data'


@dataclass(frozen=True)
class Prompt:
    number: str
    text: str
    tools: tuple


def summary_report():
    return Prompt('02', (DATA / 'summary_report.md').read_text(),
                  (SUBMIT_LR,))


def experiment_report():
    return Prompt('01', (DATA / 'experiment_report.md').read_text(), (EXPERIMENT_REPORT, SUBMIT_LR))


def no_reruns():
    return Prompt('no_reruns', (DATA / 'no_reruns.md').read_text(), (SUBMIT_LR,))


def invalid_lr():
    return Prompt('invalid_lr', (DATA / 'invalid_lr.md').read_text(), (SUBMIT_LR,))
