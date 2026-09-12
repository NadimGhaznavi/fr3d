"""Reward summaries share evidence selection but use reward-grid distances."""

from copy import deepcopy
import random
import unittest

from fr3d.app.whole_config.configuration import Configuration, REWARD_PAIR, REWARD_PATHS
from fr3d.app.whole_config.reward_history import _grid_position, summarize_reward_history


class RewardSummaryTests(unittest.TestCase):
    def setUp(self):
        self.configuration = Configuration('pages/snake-lab-schemas/simulation-config-v2.schema.json')
        self.gold = {'config': self.configuration.baseline(), 'high_score': 0}
        self.gold['config']['game']['rewards'].update(closer_to_food=0, further_from_food=0)
        for path, axis in zip(REWARD_PATHS, ((0, 10, 20, 30), (-4, -3, -2, -1, 0))):
            self.configuration.pair_values[REWARD_PAIR][path] = axis

    def row(self, closer=0, further=0, score=0, seed=None, differences=None):
        return {'closer_to_food': closer, 'further_from_food': further,
                'high_score': score, 'seed': self.gold['config']['seed'] if seed is None else seed,
                'other_setting_differences': differences or {}}

    def summarize(self, rows):
        return summarize_reward_history(rows, self.gold, self.configuration)

    def test_nearby_selection_uses_each_axes_grid_steps(self):
        rows = [self.row(), self.row(10, 0), self.row(0, -2), self.row(0, -3), self.row(0, -4)]
        groups = self.summarize(rows)['groups']
        nearby = [(row['closer_to_food'], row['further_from_food']) for row in groups
                  if 'nearby_alternative' in row['selection_reasons']]
        self.assertEqual(nearby, [(10, 0), (0, -2), (0, -3)])

    def test_uneven_off_grid_and_fixed_axis_distances(self):
        for value, expected in ((0, 0), (2, 1), (10, 2), (6, 1.5), (-2, -1), (18, 3)):
            self.assertEqual(_grid_position(value, (0, 2, 10)), expected)
        self.assertEqual(_grid_position(3, (2,)), 3)
        self.assertEqual(_grid_position(3, None), 3)

    def test_bounds_statistics_background_separation_and_determinism(self):
        seed = self.gold['config']['seed']
        rows = [self.row(score=0), self.row(score=20), self.row(score=40, seed=seed - 1)]
        rows += [self.row(i, -1, score=100-i) for i in range(1, 31)]
        rows += [self.row(score=900+i, differences={'epsilon.decay': i / 100}) for i in range(10)]
        rows += [self.row(1, -1, score=80, seed=seed+i) for i in range(1, 10)]
        result = self.summarize(rows)
        shuffled = deepcopy(rows)
        random.Random(7).shuffle(shuffled)
        self.assertEqual(result, self.summarize(shuffled))
        self.assertLessEqual(result['selected_groups'], 12)
        self.assertGreater(result['omitted_groups'], 0)
        gold = result['groups'][0]
        self.assertEqual((gold['run_count'], gold['seed_count']), (3, 2))
        self.assertEqual((gold['mean_score'], gold['seed_mean_score']), (20, 25))
        self.assertEqual(gold['current_seed_results']['mean_score'], 10)
        repeated = next(row for row in result['groups'] if row['closer_to_food'] == 1)
        self.assertEqual(repeated['omitted_seed_count'], 6)
        reasons = {reason for row in result['groups'] for reason in row['selection_reasons']}
        self.assertEqual(reasons, {'active_gold_pair', 'nearby_alternative', 'nearby_poor_performer',
                                  'strong_comparable_performer', 'broader_historical_performer'})
        for row in result['groups']:
            self.assertLessEqual(len(row['seed_results']), 4)
            self.assertEqual(row['seed_count'], len(row['seed_results']) + row['omitted_seed_count'])

    def test_empty_history(self):
        self.assertEqual(self.summarize([])['groups'], [])
