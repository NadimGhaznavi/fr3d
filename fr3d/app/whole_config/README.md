# Configuration search

The search loop selects a search dimension before building the LLM report.
`epsilon_pair` replaces the individual `epsilon.initial` and `epsilon.decay`
dimensions. `reward_pair` replaces `game.rewards.closer_to_food` and
`game.rewards.further_from_food`. Every other searchable parameter remains an
individual dimension. `PAIR_PATHS` defines the two supported pairs; each pair has
its own submission tool and prompt, with shared search and reporting behavior.

The loop waits until Snake Lab is idle before building reports or querying the
LLM, so simulation training and LLM inference run sequentially. It accounts for
the completed run, promotes gold, and handles seed rotation before selecting the
next candidate. Restarts also wait for the recovered simulation to finish.
A valid candidate is checkpointed before submission, and the final busy and
duplicate checks still protect against another simulation starting meanwhile.

1. `SearchStore.gold()` reads the best completed run for the highest recorded seed from MariaDB, using maximum
   episode score and the existing completion-time and run-ID tie breakers.
2. `SearchStore.parameter_values()` queries each dimension directly. SQL matches
   every configuration column outside the selected dimension to the active
   baseline, groups by the selected value or pair, and counts completed runs and
   the baseline row. It does not read episode scores. All recorded run statuses
   reserve configurations, as in the final duplicate check.
3. `assess_parameters()` checks that the baseline is present and compares used
   choices with the schema. Missing baseline history is an error, not exhaustion.
   Finite pairs enumerate a planned grid without full-schema candidate filtering.
   Bounded continuous pairs have no grid or finite remaining count.
   Unbounded, non-enumerable paired-field schemas fail during configuration loading. Fixed paired
   fields remain part of the pair, with their required values.
4. Each `SearchLoop` owns a `RoundRobinSelector`. It cycles through hidden size,
   sequence length, batch size, learning rate, gamma, epsilon pair, and reward
   pair, skipping exhausted finite grids. Each selected dimension advances the
   cursor once; dialogue retries stay within that turn. Gold changes preserve
   the cursor. Search checkpoints preserve its position across restarts.
5. Selection returns the parameter, initial-prompt flag, remaining count, and
   submission arguments when exactly one choice remains. The loop uses this
   result directly. A sole finite value or pair is applied to the active gold
   baseline and submitted without building a report or calling the LLM.
6. Multiple choices and continuous dimensions use the LLM. Only this path calls
   `SearchReports.parameter_report()` to fetch matching episode scores and format
   history. Finite pair reports include axes, eligible pairs, and a score table;
   continuous pairs list observations with bounds and statuses. Reports do not
   control automatic submission. Pair tools require both arguments, and all
   fields outside the selected dimension stay fixed.
7. Both decision paths check numeric types, finite values, bounds, call structure,
   fixed fields, and permitted changes,
   recheck whether Snake Lab is busy, and reject duplicate configurations at the
   submission boundary. The trace records both selected values, selection source,
   validation, baseline and best-ever gold IDs, and confirmed submission run ID.

Selection logs include used and completed choices, legal and remaining counts,
and eligibility. `selection_exhausted` means all planned finite grids from
that baseline are used. V2 learning rate is continuous from 0.0005 through 0.0050;
gamma and both epsilon values are also continuous within their bounds. Their
counts are unknown and they stay eligible, preventing grid-based exhaustion. It does not mean every schema combination has been tested.
The loop marks that baseline as a local dead end and tries the previous gold.

Previous golds are strict record highs reconstructed in completion order from
completed runs; tied scores and non-gold runs are not backtracking targets.
Within each seed, best-ever gold stays unchanged until beaten. The active baseline stays in use
across iterations, and a new best-ever gold becomes the active baseline.
Dead-end flags and the active backtracking baseline are checkpointed in Fr3d
and restored after restart. Once all previous golds are exhausted,
the loop waits until stopped. It does not explore non-gold baselines.

During backtracking the report's `gold` field holds the active baseline used by
candidate construction. `best_gold` and `search_context` identify the best-ever
result separately. Pair history and automatic selections use the active baseline.

`SearchStore` owns the direct database connection and SQL. `SearchReports` extends
it with score history and report construction; no HTTP report server participates
in selection. SQL identifiers come from the bundled schema and values are bound
parameters. The bundled v2 schema supplies bounds and planned grids.
Local tools and validation omit step, enum-membership, and cross-field checks.
In-bounds off-grid proposals may reach Snake Lab; server rejection propagates
through the existing error flow and never establishes a submitted experiment.
Snake Lab enforces full configuration validity using its standard validator.
V2 has no decimal `multipleOf` constraints or custom decimal-step workaround.

Search accounting migrations affect only the Fr3d database. No Snake Lab code,
schema, simulation data, or API changes are required.

## Export current gold

From the checkout, with MariaDB running:

```sh
sudo venv/bin/python scripts/export-gold.py --output /tmp/golden-config.json
```

Fr3d, the report server, and the LLM services can be stopped. The script reads
the database directly and does not manage services or submit a simulation.
It exports only the simulation configuration, using `SearchStore.gold()`:
the best completed run for the highest recorded seed, with the usual tie breakers.
This is the best gold for that seed, even if search has backtracked to an older
baseline. If that seed has no completed scored run, the command fails without
writing the output file.

Omit `--output` to print JSON to stdout. Run ID, seed, and score go to stderr.
`--env-file` and `--unix-socket` override the usual database connection settings.
The output file is replaced on a successful export.

## Seed rotation

After three complete round-robin cycles without a strict gold improvement, submit
current gold with `seed + 1`. All other configuration values stay unchanged. Its
completed high score becomes the new seed's score to beat, even when lower.
Rotation and the completed baseline score are logged in `fr3d.log` as well as the
decision trace; the new baseline is appended to the gold archive.

A cycle is a pass through the ordered dimensions, with exhausted and converged
dimensions skipped. Its final submitted experiment must complete before the cycle
counts. Automatic pair experiments count too; busy checks, duplicates, and failed
submissions do not count. A promotion immediately resets stagnation and marks its
cycle improved. Existing convergence reopening continues within a seed. Rotation
clears convergence windows, dead ends, and the cursor after the baseline completes.

All parameter reports include `value_results`: finite dimensions list their grid,
while continuous dimensions list values observed on the current seed or in qualifying
history. Each entry keeps current-seed `results` (or `UNTESTED`) separate from
`history`, an ascending list of completed-run high scores from other seeds with
all settings outside the selected dimension matching. Missing scores are omitted;
zero and repeated scores are retained. Historical observations do not change
eligibility or restrict continuous choices to the observed values.

Gold and previous-gold queries use only the active seed. Current results and
duplicate checks include seed. The highest seed in the configurations table is
the active seed, including queued baseline runs: after restart, existing busy and
unfinished-run checks prevent searching before that baseline completes. Failures
retain the existing stop-on-error behavior. The cursor, stagnation counters,
and convergence windows now survive restarts through Fr3d search checkpoints.


## Persistent search accounting

`SearchStateDb` uses the normal `FR3D_DB_*` credentials and the Fr3d MariaDB
schema. `SearchStore` continues its existing read-only queries against Snake Lab.
Installation and upgrade create these InnoDB tables without clearing existing
state or changing credentials:

| Table | Contents |
| --- | --- |
| `search_state` | Singleton versioned checkpoint: active seed, gold and backtracking baseline snapshots and run IDs, dead ends, parameter order, round-robin cursor, cycle flags, stagnant-cycle count, and pending completion accounting. |
| `search_parameter_state` | Per-parameter rolling score window and convergence flag. |
| `search_steps` | Parameter, initial baseline, seed-rotation, and cancellation-recovery attempts: `running` or `completed`, proposed configuration, submission history watermark, run ID, cycle metadata, outcome, and timestamps. |

Fr3d records a running step before calling the model, then records its exact
configuration and the latest simulation history ID before submitting. On restart,
it resumes that parameter. If a submission reply was lost, a matching configuration
recorded after the saved history ID identifies the submitted run. An active
simulation is allowed to finish; a completed result is accounted for; an attempt
that never reached Snake Lab is submitted using the saved configuration. If the
model call was interrupted before producing a configuration, it is rerun for the
same parameter. A cancelled run is retried with its exact recorded configuration
and keeps the original pending accounting. Failed runs still stop the loop.

Completing a step saves gold, convergence, cycle accounting, and the step's
`completed` status in one transaction. Each completed LLM-selected tweak enters
its parameter's rolling three-tweak window; improvement below two points marks
it converged. Automatic submissions still count toward cycles but not those
windows. Reopening all eligible converged parameters and rotation after three
stagnant cycles retain their existing rules.

A database named lock serializes search decisions across Fr3d processes, and
checkpoint revisions reject stale writes. A unique key allows only one running
step; simulation run IDs are unique within the step ledger. They are references,
not foreign keys into Snake Lab. Gold archive writes are atomic and deduplicated
by run ID, so replay after a transaction failure does not duplicate promotions.
Diagnostic trace messages may repeat during recovery; they do not drive accounting.

### Event history

When a completed seed rotation establishes the new golden seed, `SearchStateDb`
writes `seed_generated` through `fr3d.app.event_log.EventLog` in the same transaction
as the accounting checkpoint. Its payload contains `seed`, `reason` (currently
`no_new_high_score`), and `rounds_without_high_score`, taken from the saved cycle
count before it resets. Candidate calculation and submission do not emit this
event. An event insertion failure rolls back the checkpoint and propagates to
the caller.

Install and upgrade create `event_type`, `event_log`, and `event_log_data` in
Fr3d's database. Definitions are immutable: repeat installation accepts an
identical definition and rejects a conflicting definition. Runtime uses the
existing database-wide SELECT/INSERT grants; application code never updates or
deletes history or creates definitions. Existing file logs remain available.

`EventLog(database, provider='fr3d', version=1).write(...)` resolves the exact
provider/name/version and accepts JSON-compatible payload values. Occurrence
timestamps are UTC. Without a session, it commits its own transaction; with
`session=...`, it leaves commit and rollback to the caller. The caller must roll
back after a database failure, and returned IDs are provisional until commit.
Duplicate occurrences are allowed; reading and browsing are outside v1 scope.

The first startup with empty accounting tables recovers the current seed and gold
from existing simulation history and starts fresh counters. Previously lost
in-memory counters cannot be reconstructed. Later restarts restore saved progress.
Changing the ordered search dimensions requires an explicit state migration;
Fr3d stops rather than interpreting an old cursor against a different order.

To add only the accounting schema to an existing DEV install, from the checkout:

```sh
sudo venv/bin/python -c 'from scripts.install import ensure_search_state_schema; ensure_search_state_schema()'
```

The account retains its existing journal permissions and receives `SELECT`,
`INSERT`, and `UPDATE` on the three accounting tables. Runtime needs no schema
creation or deletion privilege. Normal `upgrade.sh` applies the same additive
migration. No services are started by the schema-only command.

Restart and rollback tests use fake simulation history. Optional MariaDB tests
create uniquely named disposable tables only in the DEV `fr3d` schema, use Fr3d's
credentials for accounting, then remove the test tables and temporary grants:

```sh
sudo env FR3D_TEST_MARIADB=1 PYTHONPATH=tests:fr3d/mcp-tools venv/bin/python -m unittest test_search_state_mariadb -v
```
