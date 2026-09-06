# Nadim-facing report viewer

## LLM decision logs

Automatic learning-rate decisions write a correlated trace to
`/opt/fr3d/logs/llm-server.log`. Each event contains a `decision_id`; actual HTTP
requests also have a `request_number` that increases across historical lookups
and duplicate-rate retries within that decision.

- `decision_started` means checks have begun, not that the model was called.
- `llm_request` includes the exact outgoing JSON payload: system/user messages,
  tool definitions, and generation settings. Authorization headers are omitted.
- `llm_response` includes the full response body, HTTP status, and elapsed seconds.
  `llm_tool_call` extracts the finish reason, tool name, and arguments.
- `lookup_started`, `lookup_result`, and `lookup_failed` describe automatic
  historical report reads, including those that bypass the MCP wrapper.
- `submission_started`, `submission_result`, `duplicate_rejected`, and
  `simulation_submitted` connect proposals to the resulting run or retry.
- `decision_failed` and `decision_finished` record the final outcome, including
  cancellation and release initialization without a model call.

Events are single-line JSON after the normal timestamp/level/logger prefix;
embedded newlines are escaped. Search for a decision ID to follow its exchange.
These traces capture automatic loop requests. Native llama-server diagnostics
and web-chat request handling remain in `journalctl -u llm-server.service`;
MCP wrapper logs alone do not capture the complete web-chat prompt.

```sh
tail -f /opt/fr3d/logs/llm-server.log
```

`LearningRateReport` is an object with per-instance `connection_factory` and
`template_path` dependencies. Call `generate_latest_report()` for JSON-safe data
from the latest three runs, or `render_report(experiments)` for selected results.
The Markdown methods remain available for the browser and standalone CLI. Loading,
validation, rendering, and duplicate lookup are methods on the class. The loop,
server, and viewer use report instances; `dialogue.learning_rate` remains a
compatibility adapter for the standalone API.

Prefer objects with explicit dependencies for new application components.

The **Best / worst** navigation link opens `/best-worst/`, showing up to ten
highest-scoring and ten lowest-scoring completed simulations. Fr3d can retrieve
the same JSON data through `view_best_worst_report` on `snakelab_tool` with no
arguments. It follows the same read-only MCP → ZMQ → Fr3d path as the latest
report and does not require a pending decision.

Rankings use `simulation_runs.high_score`, the final high score persisted by
Snake Lab, excluding incomplete statuses and missing scores. Two ordered,
limited queries retrieve run summaries without loading episode histories.
Ties use ascending numeric run ID. Rankings span all versions and configurations,
so rows include version and completed epoch count alongside learning rate.
Each table shows up to ten rows and can overlap with the other table.

Both ranking and comparison reports show duration in seconds (three decimal
places), calculated from `completed_at - started_at`. This excludes queue time
and includes pauses. Missing timestamps or completion before start display
`null` in JSON reports and `N/A` in the Markdown web comparison, not zero. No database migration is needed. Deploy and restart the report,
Fr3d agent, and LLM services to load the updated pages, handlers, and MCP tool.

The same `fr3d-report.service` also serves Fr3d's Journal at `/journal/`.
Web and MCP entry views append a blank line and an indented `--Fr3d` signature
when rendering. This applies to existing and new entries without changing the
stored journal text.
Use the navigation links to switch between the report and journal. Entries are
listed newest first, ten per page, with UTC timestamps and previous/next links.
Select a title to read its Markdown at `/journal/entries/<id>`; refresh reloads
the current page. Empty journals, missing entries, and database failures have
explanatory pages.

The journal viewer reuses `JournalApp.view_entries` and the configured Fr3d
database's shared `journal_entries` table; there is no author filter in the
current schema. Reads run in a worker thread and do not require the Fr3d agent
or model to be running. Titles and embedded HTML are escaped, and Markdown
images are disabled. The interface provides no write or delete actions.
It uses the existing service, credentials, listener, and installation path.
After deploying these changes, restart `fr3d-report.service`.

During web chat, Fr3d can call `view_latest_report` on the existing `snakelab_tool`
MCP server with no arguments. It reads the latest three completed, comparable
runs through MCP → ZMQ → `Fr3dServer` → the shared report generator and returns
`status: ok` with a JSON object in `report`, or `report_unavailable` with an explanation.
It works with learning-rate automation disabled and never creates a pending
decision, calls the model, or submits a simulation. The report's task instructions
are preview content, not a new submission request. After upgrading, restart
`fr3d-server.service` and `llm-server.service` to load the handler and MCP tool.

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
The automated loop serializes the comparison as JSON in the user message,
alongside the existing system message. It preserves template context and task
instructions, score/loss summaries, high-score milestones and loss changes,
learning rates, run IDs, versions, epoch counts, and durations. Missing numeric
values are `null`. Duplicate-run follow-ups also contain JSON reports.
`LearningRateLLM` sends the messages to the local
`/v1/chat/completions` endpoint, with `submit_learning_rate` and the optional
read-only `view_best_worst_report` function. The report template explains when
to use the historical ranking. Submission takes:

```json
{"learning_rate": 0.003}
```

The function is `submit_learning_rate`. Its object schema requires only that numeric
argument and disallows additional properties. The request forces that function,
disables parallel tool calls, and rejects text-only, malformed, multiple, or
truncated calls. The local model/server must support Chat Completions function
calling. `LLAMA_URL`, `LLAMA_MODEL`, and optional `LLAMA_API_KEY` override the
same defaults as `scripts/ask_qwen.py`. Requests use temperature 0.2, at most
4096 generated tokens per response, and a cancellable 240-second deadline for
the entire exchange. The model may request the historical report once per
proposal. Fr3d runs the shared ranking generator in a worker thread, appends
the assistant tool call and matching tool result to the conversation, and
then offers only `submit_learning_rate`. Lookup failure returns an error to
the model so it can use the original comparison. Repeated lookups are rejected.

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
