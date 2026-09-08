"""Assess matching database values, then choose the least explored parameter."""

from dataclasses import dataclass
import random

from .configuration import PAIR_PATHS
from .value_space import availability, exhausted


@dataclass(frozen=True)
class ParameterAssessment:
    parameter: str
    used: frozenset
    completed: frozenset
    legal_count: int | None
    remaining_count: int | None

    @property
    def eligible(self):
        return self.remaining_count != 0


def assess_parameters(configuration, store, gold, trace=None):
    assessments = []
    for parameter, field in configuration.parameters.items():
        rows = store.parameter_values(gold, parameter)
        # Missing gold is inconsistent data, never evidence of exhaustion.
        if not any(row['gold_count'] for row in rows):
            raise ValueError(f'Gold is missing from matching configuration history: {parameter}')
        used = frozenset(row['value'] for row in rows)
        completed = frozenset(row['value'] for row in rows if row['completed_count'])
        if parameter in PAIR_PATHS:
            legal = set(configuration.legal_pairs(gold['config'], parameter))
            total, remaining = len(legal), len(legal - used)
        else:
            total, remaining = availability(field, used)
        assessment = ParameterAssessment(parameter, used, completed, total, remaining)
        assessments.append(assessment)
        if trace is not None:
            trace.record(
                'parameter_assessed', parameter=parameter, gold_run_id=gold['run_id'],
                used_values=sorted(used), completed_values=sorted(completed),
                legal_count=total, remaining_count=remaining,
                status='eligible' if assessment.eligible else 'exhausted',
            )
    return assessments


def choose_parameter(assessments, choose=random.choice):
    candidates = [item for item in assessments if item.eligible]
    if not candidates:
        return None
    minimum = min(len(item.completed) for item in candidates)
    return choose([item for item in candidates if len(item.completed) == minimum])


def select_parameter(configuration, store, gold, choose=random.choice, trace=None):
    if trace is not None:
        trace.record('selection_started', gold_run_id=gold['run_id'],
                     searchable_parameters=len(configuration.parameters))
    assessments = assess_parameters(configuration, store, gold, trace)
    selected = choose_parameter(assessments, choose)
    if selected is None:
        if trace is not None:
            trace.record('selection_exhausted', gold_run_id=gold['run_id'],
                         assessed_parameters=len(assessments),
                         scope='search_dimension_changes_from_current_gold')
        return None
    initial = selected.completed == {configuration.value(gold['config'], selected.parameter)}
    return selected.parameter, initial
