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
        if not re.fullmatch('[0-9a-f]{32}', identity):
            raise ValueError('Invalid report ID')
        return json.loads((self.directory / (identity + '.json')).read_text(encoding='utf-8'))
