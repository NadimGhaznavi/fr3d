import json
import unittest
from copy import deepcopy
from unittest.mock import MagicMock

from fr3d.app.ReleaseInitialization import release_replays


def row(id, version='old', rate=.001, status='completed'):
    return dict(id=id, project_version=version, status=status,
                config=json.dumps({'epochs': 500, 'seed': 1970,
                                   'training': {'learning_rate': rate, 'gamma': .96}}))


class ReleaseInitializationTest(unittest.TestCase):
    def replay(self, rows):
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value.fetchall.return_value = rows
        result = release_replays('new', connection_factory=lambda: connection)
        connection.close.assert_called_once()
        return result

    def history(self):
        return [row(i, rate=i / 1000) for i in range(1, 5)]

    def test_new_release_replays_latest_three_with_exact_configs_in_order(self):
        rows = self.history()
        self.assertEqual(self.replay(rows), [json.loads(r['config']) for r in rows[-3:]])

    def test_partial_queue_and_restart_preserve_original_source_boundary(self):
        rows = self.history() + [row(5, 'new', .002), row(6, 'new', .003, 'queued')]
        self.assertEqual(self.replay(rows), [json.loads(row(7, rate=.004)['config'])])

    def test_full_queue_is_not_submitted_again(self):
        rows = self.history() + [row(5, 'new', .002, 'running'),
                                row(6, 'new', .003, 'queued'), row(7, 'new', .004, 'queued')]
        self.assertEqual(self.replay(rows), [])

    def test_completed_initialization_allows_learning_to_continue(self):
        rows = self.history() + [row(i + 3, 'new', i / 1000) for i in range(2, 5)]
        self.assertEqual(self.replay(rows), [])

    def test_failed_replay_is_retried_without_replaying_successes(self):
        rows = self.history() + [row(5, 'new', .002), row(6, 'new', .003, 'failed'),
                                row(7, 'new', .004)]
        self.assertEqual([c['training']['learning_rate'] for c in self.replay(rows)], [.003])

    def test_repeated_configs_require_matching_number_of_replays(self):
        rows = [row(i) for i in range(1, 4)] + [row(4, 'new')]
        self.assertEqual(len(self.replay(rows)), 2)

    def test_insufficient_history_and_changed_fixed_parameters_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'three preceding'):
            self.replay(self.history()[:2])
        rows = deepcopy(self.history())
        config = json.loads(rows[-1]['config'])
        config['seed'] = 42
        rows[-1]['config'] = json.dumps(config)
        with self.assertRaisesRegex(ValueError, 'parameters other than'):
            self.replay(rows)

    def test_mixed_old_versions_can_be_replayed_on_one_new_version(self):
        rows = self.history()
        rows[-1]['project_version'] = 'intermediate'
        self.assertEqual(len(self.replay(rows)), 3)


class LiveVersionTest(unittest.TestCase):
    def test_live_version_is_read_from_health(self):
        from fr3d.server.Fr3dServer import Fr3dServer
        server = MagicMock()
        server.snake_lab_request.return_value = {'project_version': '0.10.10'}
        self.assertEqual(Fr3dServer.snake_lab_version(server), '0.10.10')
        server.snake_lab_request.assert_called_once_with('health', {})

    def test_missing_or_invalid_live_version_prevents_initialization(self):
        from fr3d.server.Fr3dServer import Fr3dServer
        server = MagicMock()
        for version in (None, '', 12):
            server.snake_lab_request.return_value = {'project_version': version}
            with self.assertRaisesRegex(ValueError, 'upgrade Snake Lab first'):
                Fr3dServer.snake_lab_version(server)
