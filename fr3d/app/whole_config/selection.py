"""Assess matching database values, then choose the next round-robin dimension."""

from dataclasses import dataclass
from collections import deque
from fractions import Fraction

from .configuration import PAIR_PATHS
from .value_space import availability, finite_values


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


@dataclass(frozen=True)
class ParameterSelection:
    parameter: str
    initial: bool
    remaining_count: int | None
    automatic_arguments: dict | None


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
            pairs = configuration.legal_pairs(gold['config'], parameter)
            if pairs is None:
                total, remaining = None, None
            else:
                legal = set(pairs)
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


class ParameterConvergence:
    """Rolling three-tweak windows, checkpointed with search completion accounting."""

    def __init__(self):
        self.windows = {}
        self.converged = set()

    def completed(self, parameter, score_before, high_score, trace=None):
        window = self.windows.setdefault(parameter, deque(maxlen=3))
        window.append(score_before)
        improvement = high_score - window[0]
        if len(window) == 3 and improvement < 2:
            self.converged.add(parameter)
            if trace is not None:
                trace.record('parameter_converged', parameter=parameter, status='CONVERGED',
                             tweaks=3, starting_high_score=window[0],
                             high_score=high_score, improvement=improvement)

    def reopen_if_needed(self, assessments, trace=None):
        eligible = {item.parameter for item in assessments if item.eligible}
        if eligible and eligible <= self.converged:
            self.windows.clear()
            self.converged.clear()
            if trace is not None:
                trace.record('parameter_convergence_reset', reason='all_eligible_parameters_converged')


class RoundRobinSelector:
    """One checkpointed cursor per search loop; baseline changes preserve position."""

    def __init__(self, convergence=None):
        self.next_index = 0
        self.cycle_end = False
        self.convergence = convergence if convergence is not None else ParameterConvergence()

    def choose(self, assessments, trace=None):
        self.cycle_end = False
        self.convergence.reopen_if_needed(assessments, trace)
        for offset in range(len(assessments)):
            index = (self.next_index + offset) % len(assessments)
            if assessments[index].parameter in self.convergence.converged and trace is not None:
                trace.record('parameter_skipped', parameter=assessments[index].parameter,
                             status='CONVERGED')
            if (assessments[index].eligible
                    and assessments[index].parameter not in self.convergence.converged):
                self.cycle_end = not any(
                    item.eligible and item.parameter not in self.convergence.converged
                    for item in assessments[index + 1:])
                self.next_index = 0 if self.cycle_end else index + 1
                return assessments[index]
        return None

    def __call__(self, configuration, store, gold, trace=None):
        return select_parameter(configuration, store, gold,
                                lambda items: self.choose(items, trace), trace)


def choose_parameter(assessments):
    return next((item for item in assessments if item.eligible), None)


def select_parameter(configuration, store, gold, choose=choose_parameter, trace=None):
    if trace is not None:
        trace.record('selection_started', gold_run_id=gold['run_id'],
                     searchable_parameters=len(configuration.parameters))
    assessments = assess_parameters(configuration, store, gold, trace)
    selected = choose(assessments)
    if selected is None:
        if trace is not None:
            trace.record('selection_exhausted', gold_run_id=gold['run_id'],
                         assessed_parameters=len(assessments),
                         scope='search_dimension_changes_from_current_gold')
        return None
    initial = selected.completed == {configuration.value(gold['config'], selected.parameter)}
    arguments = None
    if selected.remaining_count == 1:
        if selected.parameter in PAIR_PATHS:
            remaining = set(configuration.legal_pairs(gold['config'], selected.parameter)) - selected.used
            arguments = configuration.pair_arguments(selected.parameter, remaining.pop())
        else:
            # Use the same exact numeric comparison as availability().
            used = {Fraction(str(value)) for value in selected.used}
            value = next(value for value in finite_values(configuration.parameters[selected.parameter])
                         if Fraction(str(value)) not in used)
            arguments = {'value': value}
    return ParameterSelection(selected.parameter, initial, selected.remaining_count, arguments)
