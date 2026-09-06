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
Fr3d database by default. The learning-rate report explicitly selects the SnakeLab database.


# Automated learning-rate experiment

`Fr3dServer.run()` starts `LearningRateLoop` and cancels it on shutdown. Every
five seconds it checks `simulation.active` at `DSnakeLab.ENDPOINT`. Running,
paused, cancelling, and queued simulations are busy. Status errors are logged
and never treated as an idle service. A separate decision task allows polling
and journal requests to continue while the model is thinking.

When idle, `LearningRateReport` reads the latest three completed runs by descending
`simulation_runs.id`, then presents them oldest first. It queries episodes using
the run UUID and the installer-provisioned Fr3d database account. Three complete,
comparable runs are required: project version and every configuration field
except `training.learning_rate` must match. Missing or incompatible history is
logged and retried on a later poll. The first valid comparison fixes the internal
baseline for the lifetime of this server process.

The report template is packaged at `fr3d/app/learning-rate.md`, based on
`notes/learning-rate.md`. It includes rates, score statistics, cumulative high-score
progression, and loss summaries. No seed or full configuration is sent to the model.
`LearningRateLLM` sends this report as the sole message to the local
`/v1/chat/completions` endpoint, with one function tool:

```json
{"learning_rate": 0.003}
```

The function is `submit_learning_rate`. Its object schema requires only that numeric
argument and disallows additional properties. The request forces that function,
disables parallel tool calls, and rejects text-only, malformed, multiple, or
truncated calls. The local model/server must support Chat Completions function
calling. `LLAMA_URL`, `LLAMA_MODEL`, and optional `LLAMA_API_KEY` override the
same defaults as `scripts/ask_qwen.py`. Requests use temperature 0.2, at most
4096 generated tokens, and a cancellable 240-second deadline.

The response handler executes the shared `SnakeLabTool` bridge. It is also exposed
as `snakelab_tool` in the MCP server configuration. The bridge sends only the rate
back to Fr3d over ZMQ. Fr3d requires a pending decision, validates a finite
`0 < learning_rate <= 1` (matching the published Snake Lab schema), checks for
an active simulation again, and replaces only the rate in its internal stored
configuration. It sends the full configuration through `simulation.submit` and
returns only status, rate, and run ID to the tool.

Each proposal is consumed before submission and is never retransmitted on a
failed or missing reply. The next poll checks status before beginning another
decision. Snake Lab has no idempotent submission operation or atomic
"submit only if idle" operation; another independent client can still submit
between Fr3d's final check and submission. This slice assumes Fr3d coordinates
these experiments. It does not require another MCP subprocess for its own loop:
the MCP wrapper and the loop use the same ZMQ bridge implementation.

The installer and upgrader include the runtime modules, report template, and MCP
tool under `fr3d/`. Automation starts when the updated Fr3d service starts.
Tests can construct `Fr3dServer(learning_rate_enabled=False)` to isolate other
server functionality.
