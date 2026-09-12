"""Evidence coverage, comparability, and bounds for epsilon history."""

from copy import deepcopy
import random
import unittest

from fr3d.app.whole_config.epsilon_history import summarize_epsilon_history


class EpsilonSummaryTests(unittest.TestCase):
    gold = {'config': {'seed': 10, 'epsilon': {'initial': .96, 'decay': .97}},
            'high_score': 0}

    def row(self, initial=.96, decay=.97, seed=10, score=0, differences=None):
        return {'initial': initial, 'decay': decay, 'seed': seed, 'high_score': score,
                'other_setting_differences': differences or {}}

    def test_grouping_keeps_backgrounds_and_seed_evidence_separate(self):
        rows = [self.row(score=0), self.row(score=20), self.row(seed=11, score=40),
                self.row(score=900, differences={'training.learning_rate': .002})]
        original = deepcopy(rows)
        result = summarize_epsilon_history(rows, self.gold)
        self.assertEqual((result['total_runs'], result['total_groups']), (4, 2))
        group, broader = result['groups']
        self.assertEqual((group['run_count'], group['seed_count']), (3, 2))
        self.assertEqual((group['mean_score'], group['seed_mean_score']), (20, 25))
        self.assertEqual((group['min_score'], group['max_score']), (0, 40))
        self.assertEqual(group['current_seed_results']['mean_score'], 10)
        self.assertEqual(group['selection_reasons'], ['active_gold_pair'])
        self.assertEqual(broader['mean_score'], 900)
        self.assertEqual(broader['selection_reasons'], ['broader_historical_performer'])
        self.assertEqual(rows, original)

    def test_coverage_is_bounded_deterministic_and_retains_poor_results(self):
        rows = [self.row()]
        rows += [self.row(initial=.96 + i / 10000, score=100 - i) for i in range(1, 31)]
        rows += [self.row(initial=.8, score=500, seed=seed) for seed in range(20)]
        rows += [self.row(score=1000 + i, differences={'training.batch_size': i})
                 for i in range(1, 8)]
        result = summarize_epsilon_history(rows, self.gold)
        shuffled = deepcopy(rows)
        random.Random(42).shuffle(shuffled)
        self.assertEqual(result, summarize_epsilon_history(shuffled, self.gold))
        self.assertLessEqual(result['selected_groups'], 12)
        self.assertEqual(result['omitted_groups'], result['total_groups'] - result['selected_groups'])
        self.assertGreater(result['omitted_groups'], 0)
        poor = [row for row in result['groups'] if 'nearby_poor_performer' in row['selection_reasons']]
        self.assertEqual([row['mean_score'] for row in poor], [88, 89, 90])
        strong = next(row for row in result['groups'] if row['initial'] == .8)
        self.assertIn('strong_comparable_performer', strong['selection_reasons'])
        self.assertEqual(strong['seed_count'], 20)
        self.assertEqual(strong['omitted_seed_count'], 16)
        self.assertEqual([row['seed'] for row in strong['seed_results']], [10, 0, 1, 2])
        self.assertEqual(sum('broader_historical_performer' in row['selection_reasons']
                             for row in result['groups']), 2)

    def test_empty_history_and_absent_current_seed(self):
        result = summarize_epsilon_history([], self.gold)
        self.assertEqual(result['groups'], [])
        self.assertEqual(result['total_runs'], 0)
        result = summarize_epsilon_history([self.row(seed=11)], self.gold)
        self.assertIsNone(result['groups'][0]['current_seed_results'])

    def test_seed_balanced_mean_ranks_above_a_lucky_maximum(self):
        rows = [self.row(initial=.8, seed=11, score=100)]
        rows += [self.row(initial=.8, score=0) for _ in range(9)]
        rows += [self.row(initial=.7, score=60)]
        # Add enough steady performers to exclude the lucky maximum from the
        # strongest category while retaining it as nearby evidence.
        rows += [self.row(initial=i, score=score) for i, score in ((.6, 70), (.5, 80))]
        groups = summarize_epsilon_history(rows, self.gold)['groups']
        lucky = next(row for row in groups if row['initial'] == .8)
        self.assertNotIn('strong_comparable_performer', lucky['selection_reasons'])
        steady = next(row for row in groups if row['initial'] == .7)
        self.assertIn('strong_comparable_performer', steady['selection_reasons'])
