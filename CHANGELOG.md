# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

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
