# Journal persistence

The request flow is MCP → ZMQ → `Fr3dServer` → `JournalApp` → `JournalDb` →
`DbMgr`. `JournalApp` owns validation, rate limiting, and timestamps;
`JournalDb` supplies SQL; `DbMgr` owns connections and transactions. The server
runs the synchronous application call in a worker thread.

Entries are append-only. Titles must contain 1–120 characters and entries
1–10,000 characters. Whitespace-only strings, NUL characters, and invalid Unicode
are rejected. Content is otherwise preserved, including Markdown and quotes;
SQL values use bound parameters.

The existing installer schema is sufficient: `id`, `title`, `entry`, and
`created_at`, indexed by `(created_at, id)`. Timestamps are generated in UTC
by the app after it acquires the writer lock. MariaDB `DATETIME(6)` stores them
without an offset; successful API responses include the UTC offset and inserted ID.

At most one entry may be accepted per rolling 60 seconds across the journal.
`JournalDb.transaction()` acquires a database-specific MariaDB named lock before
reading the latest entry. The lock stays held through commit or rollback and is
released by closing the connection. This also serializes writers when the table
is empty. All application writers must use this path; direct SQL can bypass the
policy. Database connections are not pooled. See the
[MariaDB lock documentation](https://mariadb.com/docs/server/reference/sql-functions/secondary-functions/miscellaneous-functions/get_lock).

Validation failures return `invalid_request`; rate-limit failures return
`rate_limited` with `retry_after_seconds`; lock acquisition failures return
`journal_busy`. These responses have `status: error` and are logged as warnings.
Unexpected database failures use the ZMQ transport's logged `handler_error`
response. Inserts are not automatically retried: a timeout or lost reply can
occur after a commit. This POC has no request deduplication.

`DbMgr(database_name=..., unix_socket=...)` supports explicit database selection
with the provisioned account. `query()` returns dictionaries, and `transaction()`
yields a session providing `query()` and `insert()`. Successful transactions
commit; failures roll back; all connections close. The journal uses the configured
Fr3d database by default. No SnakeLab application queries are implemented here.
