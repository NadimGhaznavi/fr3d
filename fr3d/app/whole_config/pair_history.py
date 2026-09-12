"""Bounded, deterministic evidence selection for pair prompts."""

import json
from statistics import mean


def _statistics(scores):
    return {'run_count': len(scores), 'mean_score': mean(scores),
            'min_score': min(scores), 'max_score': max(scores)}


def summarize_pair_history(history, *, names, baseline, current_seed, distance):
    """Keep comparable groups separate and select complementary evidence.

    Scores are per-run episode maxima. Each pair supplies its distance function.
    No score normalization against gold is needed, so a zero gold score is valid.
    """
    grouped = {}
    for row in history:
        key = (row[names[0]], row[names[1]],
               json.dumps(row['other_setting_differences'], sort_keys=True))
        grouped.setdefault(key, []).append(row)

    groups = {}
    for key, rows in sorted(grouped.items()):
        seeds = {}
        for row in rows:
            seeds.setdefault(row['seed'], []).append(row['high_score'])
        seed_results = [{'seed': seed, **_statistics(scores)}
                        for seed, scores in sorted(seeds.items())]
        current = next((row for row in seed_results if row['seed'] == current_seed), None)
        # Reserve room for current-seed evidence, then show up to three others.
        shown = ([current] if current else []) + [
            row for row in seed_results if row['seed'] != current_seed][:3]
        groups[key] = {
            names[0]: key[0], names[1]: key[1],
            'other_setting_differences': rows[0]['other_setting_differences'],
            **_statistics([row['high_score'] for row in rows]),
            'seed_count': len(seeds),
            'seed_mean_score': mean(row['mean_score'] for row in seed_results),
            'current_seed_results': current,
            'seed_results': shown, 'omitted_seed_count': len(seeds) - len(shown),
            'selection_reasons': [],
        }

    def strongest(key):
        group = groups[key]
        return (-group['seed_mean_score'], -group['seed_count'], distance(key), key)

    comparable = [key for key in groups if not groups[key]['other_setting_differences']]
    comparable_keys = set(comparable)
    gold_pair = baseline
    alternatives = [key for key in comparable
                    if key[:2] != gold_pair]
    nearby = sorted(alternatives, key=lambda key: (distance(key), key))
    selected = {}

    def include(keys, reason, count):
        for key in keys[:count]:
            selected[key] = groups[key]
            groups[key]['selection_reasons'].append(reason)

    include([key for key in comparable if key[:2] == gold_pair], 'active_gold_pair', 1)
    include(nearby, 'nearby_alternative', 3)
    # Poor means the weakest observed outcomes in the nearest 12 alternatives;
    # it does not imply statistical significance or a score below gold.
    include(sorted(nearby[:12], key=lambda key: (
        groups[key]['seed_mean_score'], distance(key), key)), 'nearby_poor_performer', 3)
    include(sorted(alternatives, key=strongest), 'strong_comparable_performer', 3)
    include(sorted([key for key in groups if key not in comparable_keys], key=strongest),
            'broader_historical_performer', 2)
    return {
        'total_runs': len(history), 'total_groups': len(groups),
        'selected_groups': len(selected), 'omitted_groups': len(groups) - len(selected),
        'group_limit': 12, 'groups': list(selected.values()),
    }
