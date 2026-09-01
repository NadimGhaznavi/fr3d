"""Private MariaDB persistence for Fr3d journal entries."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


class JournalDatabaseError(RuntimeError):
    """Raised when journal persistence fails without exposing DB details."""


@dataclass(frozen=True, slots=True)
class JournalEntry:
    id: int
    title: str
    entry: str
    created_at: datetime


def _connect():
    from database.Database import connect

    return connect()


class JournalRepository:
    """Store and retrieve journal entries without exposing generic SQL access."""

    def __init__(self, connection_factory: Callable[[], Any] = _connect) -> None:
        self._connection_factory = connection_factory

    def _connect(self):
        try:
            return self._connection_factory()
        except Exception as error:
            raise JournalDatabaseError("journal database connection failed") from error

    def create(self, title: str, entry: str) -> JournalEntry:
        created_at = datetime.now(UTC).replace(tzinfo=None)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO journal_entries (title, entry, created_at)
                    VALUES (%s, %s, %s)
                    """,
                    (title, entry, created_at),
                )
                entry_id = int(cursor.lastrowid)
            connection.commit()
        except Exception as error:
            connection.rollback()
            raise JournalDatabaseError("journal database operation failed") from error
        finally:
            connection.close()
        return JournalEntry(entry_id, title, entry, created_at)

    def list(self, limit: int) -> list[JournalEntry]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, title, entry, created_at
                    FROM journal_entries
                    ORDER BY created_at DESC, id DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cursor.fetchall()
        except Exception as error:
            raise JournalDatabaseError("journal database operation failed") from error
        finally:
            connection.close()

        entries: list[JournalEntry] = []
        for row in rows:
            try:
                entry_id = row["id"]
                title = row["title"]
                entry = row["entry"]
                created_at = row["created_at"]
            except (KeyError, TypeError) as error:
                raise JournalDatabaseError("journal database returned invalid data") from error
            if (
                isinstance(entry_id, bool)
                or not isinstance(entry_id, int)
                or not isinstance(title, str)
                or not isinstance(entry, str)
                or not isinstance(created_at, datetime)
            ):
                raise JournalDatabaseError("journal database returned invalid data")
            entries.append(JournalEntry(entry_id, title, entry, created_at))
        return entries
