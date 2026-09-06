"""Journal SQL; transactions and connections are managed by DbMgr."""

from contextlib import contextmanager
from datetime import datetime

from fr3d.database.DbMgr import DbMgr, DbSession


class JournalBusyError(RuntimeError):
    pass


class JournalDb:
    def __init__(self, manager: DbMgr | None = None, *, session: DbSession | None = None):
        self.manager = manager if manager is not None else DbMgr()
        self.session = session

    @contextmanager
    def transaction(self):
        """Serialize cooperating journal writers, including when the table is empty.

        The named lock remains held through commit/rollback. DbMgr closes the
        connection afterwards, which releases the lock. Connections are not pooled.
        """
        with self.manager.transaction() as session:
            rows = session.query(
                "SELECT GET_LOCK(CONCAT(DATABASE(), '.journal_entries.write'), %s) AS acquired",
                (1,),
            )
            if not rows or rows[0]['acquired'] != 1:
                raise JournalBusyError("Journal is busy; try again shortly")
            yield JournalDb(self.manager, session=session)

    def get_entries(self, limit: int = 1) -> list[dict]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        executor = self.session if self.session is not None else self.manager
        return executor.query(
            "SELECT id, title, entry, created_at FROM journal_entries "
            "ORDER BY created_at DESC, id DESC LIMIT %s", (limit,),
        )

    def add_entry(self, title: str, entry: str, created_at: datetime) -> int:
        if self.session is None:
            raise RuntimeError("Journal insertion requires a journal transaction")
        return self.session.insert(
            "INSERT INTO journal_entries (title, entry, created_at) VALUES (%s, %s, %s)",
            (title, entry, created_at),
        )
