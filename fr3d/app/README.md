# Nadim-facing report viewer

`fr3d-report.service` runs a separate Python web application at
`http://127.0.0.1:61980/`. Each visit or refresh reads the latest three completed
Snake Lab runs and renders the existing learning-rate Markdown report, including
tables, source run IDs, and a UTC generation timestamp. The same completeness
and comparability validation used by the report generator applies. Missing or
incompatible results produce an explanatory page; database and unexpected
failures produce a retry message and details in the service journal.

This is a current preview, not a saved record of the last model request. Viewing
it does not call Qwen, submit simulations, or require Fr3d's agent service to be
running. It uses the existing database credentials and Snake Lab read access.

Install and upgrade include the viewer, its HTML template, and dependencies.
Upgrade enables and starts the new service; fresh installation enables services
and leaves starting them to the operator. To start only the installed viewer:

```sh
sudo systemctl start fr3d-report.service
journalctl -u fr3d-report.service -n 50
```

For development, install `requirements.txt`, supply the normal `FR3D_DB_*`
environment variables (including `FR3D_DB_PASSWORD`), and run:

```sh
venv/bin/python -m fr3d.server.ReportServer
```

The default listener is local. For access from another machine, forward port
61980 over SSH, or set `FR3D_REPORT_HOST` and `FR3D_REPORT_PORT` in a systemd
override using `systemctl edit fr3d-report.service`:

```ini
[Service]
Environment=FR3D_REPORT_HOST=0.0.0.0
Environment=FR3D_REPORT_PORT=61980
```

Restart the service after editing. The viewer has no authentication or TLS;
use a trusted private network or SSH tunnel for this first pass.

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
progression, and loss summaries. Each high-score table includes the recorded loss
and its change from the previous displayed row in that run (current minus previous;
negative means a decrease). The first row's change is `N/A`, as is any change with
a missing endpoint loss. The final epoch always appears once, even when it does
not set a new high score. No seed or full configuration is sent to the model.
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

Before submitting, Fr3d checks all completed history for an identical configuration
and project version. A match returns `status: already_run`, the latest matching
run's numeric report ID, and "This simulation has already been run. Here's your
report." with the standard report rendered using only that run. No simulation is
started. The pending configuration stays available and the loop sends the message
and report back to the model for another choice. Each decision allows at most
three proposals before yielding to the next poll. Lookup or report failures
prevent submission.

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


On a SnakeLab code release, Fr3d reads `project_version` from the live `health`
response before making a learning-rate decision. Deploy the SnakeLab health
version field before this Fr3d update. Missing version information prevents
submission.

When the latest three completed runs are not on that version, initialization
copies the last three completed configurations preceding the first run on the
new version (or the latest three when the version has no runs yet). Fr3d submits
all missing configurations to SnakeLab's queue, preserving their learning rates
and every other parameter. SnakeLab handles serial execution. Source versions
may differ, but the fixed configuration and integer seed must match.

Database history fixes that boundary across Fr3d restarts. Matching completed or
active/queued runs on the new version count toward the three replays; duplicate
configurations count individually. Failed or cancelled attempts can be retried.
A submission error stops the batch, and the next idle poll reloads history before
submitting anything else. Once three new-version results are available, normal
learning-rate decisions resume with a fresh version baseline. Version identifiers
must identify distinct releases; rebuilding different code under the same version
cannot be detected by this mechanism.
