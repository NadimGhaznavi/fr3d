# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

## [0.16.0] - 2026-09-07 @ 16:39

### Fixed

- Reset epsilon conversation history after accepting a valid, unused config value;
  carry the submission outcome and a fresh report into the next cycle.
- Share context budgeting between epsilon and learning-rate conversations through
  `fr3d/app/conversation_context.py`. Reserve response tokens and 1,024 tokens of
  headroom within `DFr3d.CONTEXT_SIZE`, and evict oldest messages in complete
  tool-call/result groups while preserving the current prompt and latest feedback.
- Log estimated prompt budgets and server-reported token usage. Estimates include
  tool schemas and adapt upward from reported usage; they are not exact tokenizer
  counts. Stop locally if required context alone exceeds the estimated budget.

## [0.15.3] - 2026-09-07 @ 14:30

## [0.15.2] - 2026-09-07

### Changed

- Begin Phase II epsilon-decay search with learning rate fixed at the golden
  value, `0.00021`. Use its latest completed experiment as the configuration
  baseline and change only epsilon decay.
- Replace `FIRST_CONTACT` with `summary_report.md`. Each cycle supplies completed
  golden-LR experiment IDs, epsilon decay values, and high scores as JSON while
  preserving the same conversation thread.
- Accept choices through `submit_epsilon_decay`. Send `invalid_value.md` for
  invalid submissions and `no_reruns.md` for decay values already recorded at
  the golden LR, then wait for another choice in the same conversation.
- Replace the hard-coded `0.97` rejection with history-based duplicate checks.
  Include runs of every status at the golden LR and recheck before submission;
  values tested only at other learning rates remain available.
- Save epsilon summary snapshots for report viewing and include the new report
  module and Phase II prompts in installation validation.

### Validation

- Passed 53 tests covering epsilon selection and history filtering, conversation
  retries and persistence, learning-rate regressions, and installation lifecycle.

## [0.14.9] - 2026-09-07 @ 14:09

### Changed

- Start the service through `fr3d.app.epsilon.main_loop` to choose epsilon decay
  while holding the latest completed experiment's other settings fixed.
- Keep one conversation across experiment cycles, retry invalid values using
  `invalid_value.md`, and leave termination to the operator.
- Validate and install the epsilon entry point and prompts.

## [0.14.8] - 2026-09-07 @ 13:32

## [0.14.7] - 2026-09-07 @ 13:29

## [0.14.6] - 2026-09-07 @ 12:58

### Changed

- Keep the summary and rejected learning-rate choices in one conversation. Send
  `invalid_lr.md` for invalid submissions and `no_reruns.md` for previously used
  rates, then wait for another choice within the original conversation deadline.
- Install and validate both warning prompts. Missing submissions and timeouts
  return control to the main loop; only valid, unused rates reach Snake Lab.
- Order results by score not id in the `list-experiements.py` tool

## [0.14.5] - 2026-09-07 @ 12:13

### Changed

- Send the experiment summary with the initial LLM prompt and make one request
  per learning-rate decision. Expose only `submit_learning_rate`; remove report
  lookups and duplicate-choice retries from the active conversation flow.
- Submit only valid, unused learning rates. Missing, invalid, duplicate, or
  timed-out responses end the cycle; the main loop tries again after sleeping.
- Rename the Markdown prompts to `summary_report.md` and `experiment_report.md`,
  updating loaders and installation checks. The active flow uses only the summary
  prompt.

## [0.14.3] - 2026-09-07 @ 11:13

### Changed

- Double the LLM context size from 12,288 to 24,576 tokens.

## [0.14.2] - 2026-09-07 @ 11:06

### Fixed

- Show concise server error messages and HTTP error status in the readable LLM
  log instead of presenting failed requests as empty model responses.

### Changed

- Define the four-minute conversation deadline as `DFr3d.PROMPT_TIMEOUT`, separate
  from Snake Lab polling. Handle HTTP timeouts as incomplete prompts and log why
  a response produced no submission, including finish reason and tool-call count.

## [0.14.1] - 2026-09-07 @ 09:50

### Changed

- Limit the new LR reasoning log to the current task, loop/request identifiers,
  readable model reasoning, and the model’s response (including tool selections
  and arguments). Keep input prompts and response metadata in the interaction log.

## [0.14.0] - 2026-09-07 @ 09:36

### Changed

- Archive the previous application in `fr3d/app_legacy` and select
  `fr3d.app.learning_rate.main_loop` as the FR3D systemd entry point.
- Keep the experiment flow, prompt definitions, Markdown instructions, and LLM
  tools separate. Each prompt starts a fresh conversation; duplicate LR choices
  get at most three prompt 02 attempts before the main loop restarts.
- Share database report data through `fr3d/reporting`, with complete episode data
  in JSON and Markdown. Serve new experiment and summary views, preserving the
  old comparison at `/legacy/`.
- Save exact LLM report snapshots for viewing through the report server. Join
  interactions with a three-character main-loop ID and preserve readable reasoning.

### Fixed

- Use the existing service-name constant when the LLM watchdog requests a restart.

## [0.13.5] - 2026-09-07 @ 06:37

### Added

- New `dbdig.sh` helper to run commonly run SQL queries

## [0.13.4] - 2026-09-07 @ 06:25

- Improved startup

### Changed

- Changed the sequencing in `start-all-services.sh` and added a sleep for a
  smoother start.

## [0.13.3] - 2026-09-07 @ 06:19

### Added

- Helper scripts to start and stop the 5 services

## [0.13.2] - 2026-09-07 @ 05:51

### Summary

- Enhanced LLM logging

### Changed

- Shorten decision IDs from 32 to 8 hexadecimal characters across all three
  decision logs to keep activity lines compact.
- Move `reasoning_content` and `reasoning` text out of the JSON metadata line
  in `llm-reasoning.log` into readable blocks below it, preserving actual
  line breaks, paragraphs, and lists. Label each block by response choice
  and field name.

## [0.13.1] - 2026-09-07 @ 05:30

### Changed

- Split automatic decision logging into terse activity in `llm-server.log`,
  full prompt/tool-result data in `llm-prompts.log`, and model responses in
  `llm-reasoning.log`. Correlate files by decision ID and request number, and
  explicitly identify responses with no separate reasoning returned.

## [0.13.0] - 2026-09-06 @ 18:33

### Added

- Added correlated automatic LLM decision traces in `llm-server.log`, including
  exact request JSON, full responses, request timings, tool calls, historical
  lookup results, submissions, duplicate retries, and final outcomes. Omit
  authorization headers and number requests within each decision.

### Fixed

- Normalize log file paths before comparing handlers, preventing duplicate
  messages when multiple components reuse a logger with a `Path` argument.
- Replace the premature "Prompting the LLM" message with a decision-start
  event and record actual requests at the HTTP boundary.

## [0.12.9] - 2026-09-06 @ 18:18

### Changed

- Added a JSON comparison report for the LLM, including initial decisions,
  duplicate-run follow-ups, and `view_latest_report`. Preserve report data and
  template instructions, with `null` for missing values. The web comparison
  and standalone CLI retain their Markdown presentation.
- Changed the best/worst report from Markdown to JSON, retaining its fields and
  ranking rules. Tool responses contain a structured report object; the web
  viewer displays formatted JSON. Missing values use `null` and empty rankings
  use empty arrays.

## [0.12.8] - 2026-09-06 @ 18:03

- Qwen 3.7 Plus suggested these tweaks to the LLM prompts
  - Further refined by Qwen 3.8 Max

## [0.12.7] - 2026-09-06 @ 17:06

### Added

- Log knowledge-base page requests to the LLM server log using the `KbBrowser`
  identity.

### Changed

- Refactored the knowledge-base browser into `KbBrowser`, with an instance-owned
  document root and methods for URL resolution, Markdown validation, and page
  loading. Updated the MCP entry point and tests to use the object.

## [0.12.6] - 2026-09-06 @ 16:45

### Added

- Additional LLM server logging (MCP tool use)

### Changed

- Refactored `LearningRateReport` into an object owning its database connection
  factory and template path. Updated the loop, server, and web viewer
  to use report instances, preserving report output and the standalone API.

## [0.12.5] - 2026-09-06 @ 16:16

- Added more log messages to the llm-server

## [0.12.4] - 2026-09-06 @ 16:04

### Fixed

- Enabled LLM server logs

## [0.12.3] - 2026-09-06 @ 16:00

### Added

- Added additional logging of the MCP tool invocations


## [0.12.2] - 2026-09-06 @ 15:03

### Fixed

- Corrected the journal branding to Fr3d's Journal. Web and MCP entry views
  append a blank line and an indented `--Fr3d` signature without changing
  stored journal text.

## [0.12.0] - 2026-09-06 @ 14:23

### Added

- Added a best/worst simulation report at `/best-worst/` and through the read-only
  `view_best_worst_report` MCP tool. Rank the top ten and bottom ten completed
  runs by final high score, showing run ID, version, epoch count, learning rate,
  and duration. Include all versions and break ties by ascending run ID.

### Changed

- Referenced `view_best_worst_report` in the learning-rate prompt and made it
  callable during automated decisions. Allow one optional historical lookup
  per proposal, return its result to the model, then require rate submission
  within the existing overall deadline.
- Added elapsed simulation duration to the shared three-run comparison report.
  Both reports use completion minus start time in seconds, excluding queue time
  and including pauses; missing or reversed timestamps show `N/A`.

## [0.11.3] - 2026-09-06 @ 13:48

### Added

- Added Fr3d's Journal browser to `fr3d-report.service` at `/journal/`, with
  newest-first pages of ten entries, UTC timestamps, rendered Markdown entry
  pages, and navigation back to the learning-rate report. Reuse the existing
  read-only journal application and database access, with empty, missing-entry,
  and unavailable states.
- Added the read-only `view_latest_report` MCP tool for web chat. Return the
  current learning-rate report from the latest three completed, comparable
  runs without requiring a pending decision or starting a simulation.

### Changed

- Increased the llama-server context size from 8,192 to 12,288 tokens and
  reasoning budget from 2,048 to 4,096 tokens.
- Updated Fr3dNet's Snake Lab tool guide with latest-report access during web
  chat and clarified that viewing a report does not request a new experiment.

## [0.11.2] - 2026-09-06 @ 13:06

### Changed

- Replaced the Snake Lab tool's under-construction notice in Fr3dNet with
  instructions for submitting a learning rate, interpreting report losses,
  and handling previously completed configurations. Documented that submission
  requires a pending experiment decision.

## [0.11.1] - 2026-09-06 @ 12:55

### Added

- Added a Nadim-facing Python report viewer with its own `fr3d-report.service`,
  independent of the agent and llama-server. Each visit or refresh renders the
  existing learning-rate report from the latest three completed, comparable
  Snake Lab runs, with source run IDs, a UTC timestamp, and explanatory errors.
  The listener defaults to `127.0.0.1:61980` with configurable host and port.
- Included the report viewer, HTML template, and dependencies in installation
  and upgrade, and its service in uninstall. Upgrade enables and starts the
  new service.

### Changed

- Added recorded loss and loss change to each displayed high-score row in the
  shared LLM and web report. Change is current loss minus the previous displayed
  row's loss within the same run; negative values indicate a decrease. The
  first change and changes with either loss missing show `N/A`. Preserve the
  final-epoch row exactly once, even when it does not set a new high score.

## [0.11.0] - 2026-09-06 @ 11:21

### Added

- Initialize new SnakeLab releases by queueing the previous three completed
  configurations on the running version before learning-rate decisions resume.
  Recover partial initialization from database history and check the live version
  before submitting model proposals. Requires SnakeLab's versioned health response.

### Fixed

- Prevent repeated Snake Lab configurations from launching another simulation.
  Search completed history for the same configuration and project version and
  return the standard learning-rate report for the latest matching run with
  "This simulation has already been run. Here's your report." The model can
  choose again, with at most three proposals per decision.

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
