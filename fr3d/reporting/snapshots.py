"""Persist the exact report object sent to an LLM for later human inspection."""

import json
import re
import uuid
from pathlib import Path

from fr3d.constants.DDir import DDirDef
from .formats import to_json


class ReportSnapshots:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory is not None else DDirDef.SERVER_LOGS / 'reports'

    def save(self, data):
        content = to_json(data)
        self.directory.mkdir(parents=True, exist_ok=True)
        identity = uuid.uuid4().hex
        temporary = self.directory / (identity + '.tmp')
        temporary.write_text(content, encoding='utf-8')
        temporary.replace(self.directory / (identity + '.json'))
        return identity

    def load(self, identity):
        if not self.valid_identity(identity):
            raise ValueError('Invalid report ID')
        return json.loads((self.directory / (identity + '.json')).read_text(encoding='utf-8'))

    @staticmethod
    def valid_identity(identity):
        return bool(re.fullmatch('[0-9a-f]{32}', identity))

    def latest_summary(self):
        """Find the newest complete parameter summary, ignoring older report types."""
        files = sorted(
            ((path.stat().st_mtime_ns, path) for path in self.directory.glob('*.json')
             if self.valid_identity(path.stem)),
            reverse=True,
        )
        for modified_ns, path in files:
            data = self.load(path.stem)
            if (isinstance(data, dict) and isinstance(data.get('parameter'), str)
                    and isinstance(data.get('gold'), dict)
                    and isinstance(data.get('experiments'), list)):
                return path.stem, data, modified_ns / 1_000_000_000
        raise FileNotFoundError('No saved parameter summary report')
