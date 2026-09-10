"""Append gold promotions to Fr3d's persistent experiment history."""

import json
import os
from pathlib import Path
import tempfile

from fr3d.constants.DDir import DDirDef


class GoldArchive:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else DDirDef.SERVER_LOGS / 'gold.jsonl'

    def save(self, gold, previous):
        record = {key: gold[key] for key in ('run_id', 'config', 'high_score')}
        record['previous_gold_run_id'] = previous['run_id'] if previous is not None else None
        content = json.dumps(record, allow_nan=False) + '\n'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existing = self.path.read_text(encoding='utf-8') if self.path.exists() else ''
        if any(json.loads(line)['run_id'] == gold['run_id'] for line in existing.splitlines()):
            return
        # A promotion may be replayed after an accounting rollback. Atomic
        # replacement keeps the archive complete and run IDs make replay safe.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent,
                                             prefix='.gold-', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(existing + content)
                stream.flush()
                os.fchmod(stream.fileno(), self.path.stat().st_mode & 0o777 if self.path.exists() else 0o644)
                os.fsync(stream.fileno())
            temporary.replace(self.path)
            directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
