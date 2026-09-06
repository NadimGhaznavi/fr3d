# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

## [0.10.1] - 2026-09-06 @ 10:07

### Added

- Added a complete 500-epoch sample Snake Lab configuration with seed 1970 for
  preparing comparable initial runs by varying only the learning rate.

### Fixed

- Send `tool_choice: "required"` to the local llama-server instead of the
  named-function object it rejects. Only `submit_learning_rate` is offered;
  returned tool calls and arguments remain validated.

## [0.10.0] - 2026-09-06 @ 09:46

### Added

- Added continuous learning-rate experimentation: poll Snake Lab every five
  seconds, generate a report from the latest three completed runs when idle,
  ask the local LLM for a learning rate, and submit the next simulation.
- Added the `snakelab_tool` MCP server and `submit_learning_rate` function with
  one required numeric argument. Fr3d receives the rate over ZMQ, validates
  `0 < learning_rate <= 1`, and changes only that field in its internal baseline
  configuration. The model sees the report, not the full configuration.
- Require three completed runs with complete episode data, matching project
  versions, and identical settings except for learning rate. Preserve the seed
  and other settings throughout the automated experiment.
- Keep one decision in flight while polling and journal requests continue;
  recheck Snake Lab's status before submitting and cancel the decision on
  shutdown. Failed submissions do not automatically replay the same proposal.
- Added `scripts/ask_qwen.py`, a configurable standard-library command-line
  client for local chat completions, with optional raw JSON output.

### Changed

- Moved the shared report builder and template into the installed `fr3d/app`
  package and corrected the standalone report command's database imports.
- Added cancellable HTTP requests through `httpx`, MCP registration, runtime
  documentation, and tests covering report selection, tool validation, polling,
  shutdown, and the submission flow through a fake Snake Lab ZMQ service.

## [0.9.1] - 2026-09-06 @ 07:44

### Added

- Added a conversational Easter egg to the Snake Lab tool's knowledge-base
  page, inviting Fr3d to ask Nadim about the tool during web chat.

## [0.9.0] - 2026-09-06 @ 07:39

### Added

- Expanded Fr3dNet with pages about Snake Lab, the project goal, web chat,
  Nadim, and the planned Snake Lab submission tool.

### Changed

- Reorganized knowledge-base navigation, refreshed computing and location
  information, and removed the obsolete static journal index.

## [0.8.15] - 2026-09-06 @ 05:58

### Added

- Added journal `view_entries(url="/")` browsing with knowledge-base-style
  Markdown links, newest-first lists of ten titles, previous/next navigation,
  and individual entry pages with UTC timestamps and journal text.
- Added validated journal browse routes and parameterized database reads through
  the existing MCP, ZMQ, application, and database pipeline.

## [0.8.14] - 2026-09-06 @ 05:40

### Added

- Added `JournalApp` validation and append-only journal persistence through
  `JournalDb` and `DbMgr`, using the existing journal schema and UTC timestamps.
- Enforced a journal-wide rolling 60-second insertion limit with a MariaDB
  writer lock held through commit, including concurrent requests to an empty journal.
- Added parameterized SQL execution, transaction rollback and connection cleanup,
  and configurable database selection for future SnakeLab queries.

### Changed

- Run journal database operations outside the Fr3d event loop and return explicit
  validation, rate-limit, and busy responses. Preserve supplied server handlers.

## [0.8.13] - 2026-09-06 @ 05:19

### Fixed

- Passed the supplied journal title and entry from the ZMQ message into
  `JournalDb.add_entry()` instead of using hard-coded placeholder values.

## [0.8.12] - 2026-09-06 @ 05:16

### Changed

- Typed the journal handler input as `ZMQMsg` and logged its payload rather
  than the whole message. Journal writes still used placeholder values.

## [0.8.11] - 2026-09-06 @ 05:06

### Fixed

- Awaited journal MCP requests, aligned their method name with the Fr3d handler,
  and returned dictionary payloads over ZMQ with JSON text at the MCP boundary.
  Journal persistence remains a stub.

## [0.8.10] - 2026-09-06 @ 04:59

### Fixed

- Passed `--cors-origins` and `*` as separate llama-server command arguments,
  correcting the combined argument used by the preceding CORS releases.

## [0.8.9] - 2026-09-06 @ 04:55

### Changed

- Restored quotes around the wildcard in the combined CORS argument. The
  argument-format problem remained until 0.8.10.

## [0.8.8] - 2026-09-06 @ 04:53

### Fixed

- Restored the ops uptime target `llm-server` to match the MCP tool schema,
  while retaining `llama-server` as the process name used to calculate uptime.

## [0.8.7] - 2026-09-06 @ 04:27

### Changed

- Removed quotes around the wildcard in the combined CORS argument. The
  argument-format problem remained until 0.8.10.

## [0.8.6] - 2026-09-06 @ 04:25

### Changed

- Replaced the explicit localhost and wintermute CORS origins with a quoted
  wildcard. The option and value still occupied one command argument;
  0.8.10 corrected that format.

## [0.8.5] - 2026-09-06 @ 04:23

### Added

- Added a CORS argument listing localhost and wintermute on port 51970.
  The option and value were supplied as one command argument; 0.8.10 later
  corrected the argument format.

## [0.8.4] - 2026-09-06 @ 04:19

### Changed

- Defaulted the Fr3d and ZMQ server listeners to `127.0.0.1` using a separate
  `DFr3d.ZMQ_HOST` setting, restricting ZMQ access to the local machine.

## [0.8.3] - 2026-09-06 @ 04:12

### Changed

- Changed the requested CORS origin from wintermute to a wildcard. The option
  and value still occupied one command argument; 0.8.10 later corrected that
  format.

## [0.8.2] - 2026-09-06 @ 04:10

### Added

- Added a CORS argument for `http://wintermute:51970`. The option and value
  were supplied as one command argument; 0.8.10 later corrected that format.

## [0.8.1] - 2026-09-06 @ 04:04

### Added

- Registered the `add_journal_entry` Fr3d method and connected its initial
  handler to `JournalDb`, using placeholder title and entry values while
  journal integration was under development.

## [0.8.0] - 2026-09-06 @ 03:52

### Added

- Added a reusable synchronous `ZMQClient` for plain JSON and Fr3d `ZMQMsg`
  request/reply calls, with configurable timeouts and socket cleanup per request.

### Changed

- Delegated SnakeLab request transport in `Fr3dServer.is_simulation_running()`
  to `ZMQClient`, retaining SnakeLab response validation in the server.

## [0.7.4] - 2026-09-06 @ 03:22

### Fixed

- Moved Fr3d's ZMQ listener from port `41972` to `61970` to resolve the
  remaining port conflict.

## [0.7.3] - 2026-09-06 @ 03:13

### Fixed

- Corrected the LLM model directory to `/opt/dev/models/quantized`, matching
  the existing model storage outside the Fr3d installation tree.
- Moved Fr3d's ZMQ listener to port `41972` to avoid conflicting with
  SnakeLab's control (`41970`) and telemetry (`41971`) listeners.

## [0.7.2] - 2026-09-06 @ 03:07

### Added

- Integrated `ZMQServer` into `Fr3dServer` for server-side handler dispatch,
  transport error propagation, and signal-aware async startup and shutdown.
  No LLM client or application RPC methods are added by this integration.
- Completed the standalone async `ZMQServer` request/reply wrapper with socket
  binding, synchronous and async method handlers, error replies, receive
  timeouts, and cancellation-safe shutdown. Added usage documentation and
  loopback tests for dispatch, malformed requests, and lifecycle behavior.

### Changed

- Updated deployment for the `fr3d` package layout and the refactored directory
  and file constants, including systemd entry points, MCP imports, and runtime
  configuration copying. Database credentials remain in `/etc/fr3d/database.env`
  with root ownership, service-group access, and mode `0640`.
- This release requires uninstalling and reinstalling Fr3d. Upgrade does not
  migrate the previous layout or recreate missing credentials. Uninstall removes
  the Fr3d database and installation tree, including any models stored there;
  back up needed data and model files first. SnakeLab's database is not removed.
- Kept the ZMQ package focused on Fr3d request/reply messaging, removing unused
  copied helpers, topic-prefix configuration, and compatibility wording.

### Fixed

- Updated `scripts/new-release.sh` to use `fr3d/constants/DFr3d.py` after the
  package refactor, restoring version detection, preflight validation, and
  version updates with Git staging.
- Added deployment preflight checks for unsafe paths and invalid server syntax,
  corrected runtime and credential handling, and preserved staged model files
  when reinstalling without first removing the installation tree.
- Corrected `ZMQMsg`'s protocol-default import and numeric protocol-version
  serialization, and validated incoming message fields before dispatch.

## [0.7.1] - 2026-09-05 @ 13:39

### Changed

- Began restructuring journal persistence: simplified the MCP interface to
  title and entry, replaced journal operations with a temporary acknowledgement
  stub, and moved the database connection helper into `DbManager`.
- Moved the learning-rate prompt template from `templates/` to `notes/`.
  The report command's stale template reference was corrected in 0.10.0.

## [0.7.0] - 2026-09-05 @ 11:26

### Added

- Added `python -m dialogue.poke_fr3d` to generate a learning-rate experiment
  prompt from completed SnakeLab runs using `templates/learning-rate.md`,
  printing populated Markdown to stdout without database writes, LLM requests,
  or simulation submissions.
- Added per-run mean, median, and high scores, cumulative high-score milestones,
  and mean and final training losses calculated from stored episode data.
  Comparisons require complete episode data and matching project versions and
  configurations except for `training.learning_rate`.
- Added standalone options for selecting run IDs, templates, database credential
  files, and local MariaDB sockets, plus usage documentation and tests for
  statistics, validation, read-only queries, credentials, and CLI output.

### Changed

- Updated installation and upgrades to grant `DDatabase.USERNAME` database-wide
  `SELECT` access to `DDatabase.SNAKE_LAB_DB_NAME` (`snakelab`). Existing
  installations reapply the grant without recreating databases or changing
  credentials.
- Extended the shared database connection helper with optional database-name
  and Unix-socket overrides while preserving existing connection defaults.

## [0.6.0] - 2026-09-05 @ 09:40

### Added

- Implemented the `server.Fr3dServer` agent loop to query SnakeLab's
  `simulation.active` endpoint over ZeroMQ, waiting while a simulation is
  running, paused, cancelling, or queued.
- Added configurable SnakeLab connection settings and a five-second polling
  interval in `DFr3d`. Idle iterations log a placeholder for future LLM queries
  through `MyLog`, using the `FR3D` identity and `FRED_SERVER_LOG`.
- Added response validation and timeout handling so failed status queries are
  logged and retried rather than treated as an idle server. All iterations
  sleep between polls to avoid busy loops.
- Added the `pyzmq` dependency and tests for polling, response validation,
  retries, logging, and log-directory ownership.

### Fixed

- Allowed `fr3d-server.service` to write to `/opt/fr3d/logs` under systemd's
  filesystem restrictions, and updated installation and upgrade steps to
  ensure the agent's log directory is owned by the service account.

## [0.5.1] - 2026-09-02 @ 14:28

### Fixed

- Updated the installer to deploy the `utils` package and create
  `/opt/fr3d/logs`, allowing `LLMWatchdog` to import `MyLog` and initialize its
  log file after a fresh installation.

## [0.5.0] - 2026-09-02 @ 14:17

### Added

- Added `MyLog`, a centralized console and file logging utility that creates
  missing log directories and fails immediately when logging cannot be
  initialized.
- Added `llm-watchdog.service` and `server.LLMWatchdog`, which check the LLM
  server's `/health` endpoint every minute and restart the server when it does
  not return `{"status":"ok"}`.
- Added Fr3d website branding and logo assets.

### Changed

- Renamed `server.Fr3dServer` to `server.LLMServer` and the systemd unit from
  `fr3d.service` to `llm-server.service` to distinguish the inference server
  from the wider Fr3d project.
- Renamed the `ops.uptime` target from `qwen-service` to `llm-server` so the
  operations interface is independent of the currently configured model.
- Updated the installer and uninstaller to manage both the LLM server and its
  watchdog.
- This release requires an uninstall and fresh install; upgrading across these
  systemd unit changes with `upgrade.sh` is not supported.

## [0.4.0] - 2026-09-02 @ 05:24

- Moved the journal, knowledge-base, and weather MCP tools into `mcp-tools/` and updated runtime, installation, upgrade, and test paths.
- Added the `ops.uptime` MCP tool for llama-server and operating-system uptime.

## [0.3.2] - 2026-09-01 @ 18:17

### Added

- Added the public site's Jekyll configuration, homepage, and custom domain.

### Changed

- Reduced the default LLM context window from 65,536 to 8,192 tokens.

## [0.3.1] - 2026-09-01 @ 05:31

### Added

- Added MariaDB-backed journal storage with create and list operations,
  parameterized database access, and Markdown results.
- Added database provisioning, service credentials, and lifecycle tests.
  Upgrades preserve journal data; uninstall removes the Fr3d database.

## [0.3.0] - 2026-08-31 @ 19:34

### Added

- Added the journal MCP tool for validated, titled Markdown entries of up to
  five paragraphs, with a browsable journal index in Fr3dNet.
- Added knowledge-base guides for the journal, weather, and browser tools.

### Changed

- Updated installation, upgrades, and service write access for journal files,
  preserving journal content across upgrades.

## [0.2.1] - 2026-08-31 @ 19:15

### Added

- Added `scripts/upgrade.py` and `scripts/upgrade.sh` to refresh deployed code
  and services while preserving the virtual environment and service account.

## [0.2.0] - 2026-08-31 @ 19:13

### Added

- Added the weather MCP tool for current conditions and a three-day forecast
  by city or postal code, using Open-Meteo with input and response validation.
- Added location information to Fr3dNet and included the weather tool in
  deployment and MCP configuration.

## [0.1.1] - 2026-08-31 @ 18:47

### Fixed

- Renamed the knowledge-base MCP server to `kb` and its function to `tool`,
  removing the duplicated `kb_tool` naming in the exposed interface.

## [0.1.0] - 2026-08-31 @ 18:42

### Added

- Added the Fr3dNet Markdown knowledge base and an MCP browser for navigating
  its pages, starting at `/`.
- Added computing-environment documentation, browser tests, and MCP runtime
  dependencies and deployment configuration.

## [0.0.2] - 2026-08-31 @ 18:18

### Added

- Added the initial llama-server launcher with model, context, reasoning,
  network, and MCP configuration, plus startup validation and tests.

### Changed

- Removed the unused scheduler service and updated installation and cleanup
  for the initial LLM server deployment.

## [0.0.1] - 2026-08-31 @ 18:11

### Added

- Added the initial project scaffold, configuration constants, systemd units,
  and installation and uninstallation scripts for a dedicated Fr3d account.
- Added the release script for version updates, changelog headings, branch
  merges, annotated tags, and publication.
