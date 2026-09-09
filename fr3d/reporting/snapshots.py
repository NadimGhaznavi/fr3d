"""Persist the exact report object sent to an LLM for later human inspection."""

import json
import logging
import re
import uuid
from datetime import datetime, timezone
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

    @staticmethod
    def valid_parameter(parameter):
        return isinstance(parameter, str) and bool(re.fullmatch(r'[a-z][a-z0-9_.]{0,127}', parameter))

    def save_prompt(self, parameter, payload):
        """Replace one sample per parameter. Inspection must not stop exploration."""
        temporary = None
        try:
            if not self.valid_parameter(parameter):
                raise ValueError('Invalid parameter')
            directory = self.directory / 'prompts'
            content = to_json({'parameter': parameter,
                               'saved_at': datetime.now(timezone.utc).isoformat(),
                               'payload': payload})
            directory.mkdir(parents=True, exist_ok=True)
            temporary = directory / (uuid.uuid4().hex + '.tmp')
            temporary.write_text(content, encoding='utf-8')
            temporary.replace(directory / (parameter + '.json'))
        except (OSError, ValueError, TypeError):
            logging.getLogger(__name__).exception('Could not save latest prompt for %s', parameter)
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    def prompt_parameters(self):
        return sorted(path.stem for path in (self.directory / 'prompts').glob('*.json')
                      if self.valid_parameter(path.stem))

    def load_prompt(self, parameter):
        if not self.valid_parameter(parameter):
            raise FileNotFoundError('Unknown parameter')
        return json.loads((self.directory / 'prompts' / (parameter + '.json')).read_text(encoding='utf-8'))

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
