# Configuration search

The search loop selects a search dimension before building the LLM report.
`epsilon_pair` replaces the individual `epsilon.initial` and `epsilon.decay`
dimensions. `reward_pair` replaces `game.rewards.closer_to_food` and
`game.rewards.further_from_food`. Every other searchable parameter remains an
individual dimension. `PAIR_PATHS` defines the two supported pairs; each pair has
its own submission tool and prompt, with shared search and reporting behavior.

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
   the cursor, and restart begins at the first dimension. No cursor is persisted.
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
Dead-end flags are held for the process lifetime and logged; after restart they
are recomputed from database history. Once all previous golds are exhausted,
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

Release 0.21.0 deployment is planned as an uninstall/install of both Snake Lab and
Fr3d, starting with fresh data. This implementation adds no data migration or
automatic deletion of experiment history.

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

Gold and previous-gold queries use only the active seed. Matching reports and
duplicate checks include seed. The highest seed in the configurations table is
the active seed, including queued baseline runs: after restart, existing busy and
unfinished-run checks prevent searching before that baseline completes. Failures
retain the existing stop-on-error behavior. The cursor and stagnation counters
restart at zero; they are not persisted. Snake Lab must deploy the matching v2
schema permitting nonnegative integer seeds before running this release.
