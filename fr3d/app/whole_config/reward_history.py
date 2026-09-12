"""Reward evidence measures proximity in configured grid steps."""

from bisect import bisect_right

from .configuration import REWARD_PAIR
from .pair_history import summarize_pair_history


def _grid_position(value, values):
    """Adjacent grid values are one step apart, including uneven grids.

    Interpolate off-grid history and extrapolate using the nearest edge gap.
    Without two distinct grid values, fall back to raw parameter units.
    """
    axis = sorted(set(values or ()))
    if len(axis) < 2:
        return value
    index = max(0, min(bisect_right(axis, value) - 1, len(axis) - 2))
    return index + (value - axis[index]) / (axis[index + 1] - axis[index])


def summarize_reward_history(history, gold, configuration):
    names = tuple(configuration.parameters[REWARD_PAIR]['required'])
    baseline = configuration.value(gold['config'], REWARD_PAIR)
    axes = [configuration.pair_values[REWARD_PAIR][path]
            for path in configuration.paths(REWARD_PAIR)]
    origin = [_grid_position(value, axis) for value, axis in zip(baseline, axes)]

    def distance(key):
        return sum((_grid_position(key[index], axes[index]) - origin[index]) ** 2
                   for index in range(2))

    return summarize_pair_history(history, names=names, baseline=baseline,
                                  current_seed=gold['config']['seed'], distance=distance)
