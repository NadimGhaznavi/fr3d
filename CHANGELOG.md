# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

- Added a reusable synchronous `ZMQClient` for plain JSON and Fr3d `ZMQMsg`
  request/reply calls, with configurable timeouts and socket cleanup per request.

### Changed

- Delegated SnakeLab request transport in `Fr3dServer.is_simulation_running()`
  to `ZMQClient`, retaining SnakeLab response validation in the server.

## [0.7.4] - 2026-09-06 @ 03:22

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

## [0.3.1] - 2026-09-01 @ 05:31

## [0.3.0] - 2026-08-31 @ 19:34

## [0.2.1] - 2026-08-31 @ 19:15

## [0.2.0] - 2026-08-31 @ 19:13

## [0.1.1] - 2026-08-31 @ 18:47

## [0.1.0] - 2026-08-31 @ 18:42

## [0.0.2] - 2026-08-31 @ 18:18

## [0.0.1] - 2026-08-31 @ 18:11

### Added
