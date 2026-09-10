"""Generic append-only event history with optional caller-owned transactions."""

import json
import math
from datetime import datetime, timezone

from fr3d.database.DbMgr import DbSession


LEVELS = frozenset({'debug', 'info', 'warning', 'error', 'critical'})


def _text(value, name, limit, *, empty=False):
    if not isinstance(value, str):
        raise TypeError(f'{name} must be a string')
    if (not empty and not value) or len(value) > limit:
        raise ValueError(f'{name} must fit 1..{limit} characters' if not empty
                         else f'{name} must fit {limit} characters')


def _json_value(value, active=None):
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError('Payload numbers must be finite')
        return
    if type(value) not in (list, dict):
        raise TypeError('Payload values must be JSON-compatible')
    active = set() if active is None else active
    if id(value) in active:
        raise ValueError('Payload cannot contain circular references')
    active.add(id(value))
    try:
        if isinstance(value, dict):
            if any(not isinstance(key, str) for key in value):
                raise TypeError('Nested object keys must be strings')
            values = value.values()
        else:
            values = value
        for item in values:
            _json_value(item, active)
    finally:
        active.remove(id(value))


class EventLog:
    def __init__(self, database, *, provider: str = 'fr3d', version: int = 1):
        _text(provider, 'provider', 64)
        if type(version) is not int or not 1 <= version <= 65535:
            raise ValueError('version must be an integer in 1..65535')
        self.database = database
        self.provider = provider
        self.version = version

    def write(self, event_name: str, *, message: str | None = None,
              data: dict[str, object] | None = None, level: str | None = None,
              session: DbSession | None = None) -> int:
        """Write an occurrence. Caller-owned sessions must roll back on failure.

        With a supplied session, the returned ID is provisional until its commit.
        """
        _text(event_name, 'event_name', 64)
        if message is not None:
            _text(message, 'message', 1024, empty=True)
        if level is not None and (not isinstance(level, str) or level not in LEVELS):
            raise ValueError('Invalid event level')
        if data is not None and not isinstance(data, dict):
            raise TypeError('data must be a dictionary')
        payload = []
        for key, value in (data.items() if data is not None else ()):
            _text(key, 'payload key', 64)
            _json_value(value)
            payload.append((key, json.dumps(value, allow_nan=False)))
        if session is not None:
            return self._insert(session, event_name, message, payload, level)
        with self.database.transaction() as owned:
            return self._insert(owned, event_name, message, payload, level)

    def _insert(self, session, event_name, message, payload, level):
        rows = session.query(
            'SELECT id, default_level FROM event_type '
            'WHERE provider = %s AND name = %s AND version = %s',
            (self.provider, event_name, self.version))
        if len(rows) != 1:
            raise ValueError(f'Unknown or ambiguous event type: '
                             f'{self.provider}/{event_name}/v{self.version}')
        effective_level = rows[0]['default_level'] if level is None else level
        if effective_level not in LEVELS:
            raise ValueError('Invalid event default level')
        identity = session.insert(
            'INSERT INTO event_log (occurred_at, event_type_id, level, message) '
            'VALUES (%s, %s, %s, %s)',
            (datetime.now(timezone.utc).replace(tzinfo=None), rows[0]['id'], effective_level, message))
        for key, value in payload:
            session.insert('INSERT INTO event_log_data (event_log_id, name, value) VALUES (%s, %s, %s)',
                           (identity, key, value))
        return identity
