"""Epsilon evidence uses equal scales in initial/decay parameter space."""

from .pair_history import summarize_pair_history


def summarize_epsilon_history(history, gold):
    baseline = tuple(gold['config']['epsilon'][name] for name in ('initial', 'decay'))

    def distance(key):
        return sum((key[index] - baseline[index]) ** 2 for index in range(2))

    return summarize_pair_history(history, names=('initial', 'decay'), baseline=baseline,
                                  current_seed=gold['config']['seed'], distance=distance)
