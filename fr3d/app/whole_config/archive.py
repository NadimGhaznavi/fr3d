"""Append gold promotions to Fr3d's persistent experiment history."""

import json
from pathlib import Path

from fr3d.constants.DDir import DDirDef


class GoldArchive:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else DDirDef.SERVER_LOGS / 'gold.jsonl'

    def save(self, gold, previous):
        record = {key: gold[key] for key in ('run_id', 'config', 'high_score')}
        record['previous_gold_run_id'] = previous['run_id'] if previous is not None else None
        content = json.dumps(record, allow_nan=False) + '\n'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open('a', encoding='utf-8') as stream:
            stream.write(content)
