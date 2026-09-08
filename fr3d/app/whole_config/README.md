# Configuration search

The search loop selects a search dimension before building the LLM report.
`epsilon_pair` replaces the individual `epsilon.initial` and `epsilon.decay`
dimensions. `reward_pair` replaces `game.rewards.closer_to_food` and
`game.rewards.further_from_food`. Every other searchable parameter remains an
individual dimension. `PAIR_PATHS` defines the two supported pairs; each pair has
its own submission tool and prompt, with shared search and reporting behavior.

1. `SearchStore.gold()` reads the best completed run from MariaDB, using maximum
   episode score and the existing completion-time and run-ID tie breakers.
2. `SearchStore.parameter_values()` queries each dimension directly. SQL matches
   every configuration column outside the selected dimension to the active
   baseline, groups by the selected value or pair, and counts completed runs and
   the baseline row. It does not read episode scores. All recorded run statuses
   reserve configurations, as in the final duplicate check.
3. `assess_parameters()` checks that the baseline is present and compares used
   choices with the schema. Missing baseline history is an error, not exhaustion.
   Each pair enumerates both fields and validates each complete candidate.
   Non-enumerable paired-field schemas fail during configuration loading. Fixed paired
   fields remain part of the pair, with their required values.
4. `choose_parameter()` keeps eligible dimensions with the fewest distinct
   completed choices, choosing randomly among ties. A completed pair
   counts as one choice.
5. Only then does `SearchReports.parameter_report()` fetch matching episode scores.
   Individual-parameter reports retain their existing format. The pair report adds
   schema-derived axes, an explicit eligible-pair list, and a Markdown score table.
   Untested cells have no recorded experiment; used cells without scores show
   status. Multiple runs in a cell retain individual results and run IDs.
6. The sole remaining eligible pair bypasses the LLM. Multiple pairs use a
   dedicated prompt and either `submit_epsilon_pair(initial, decay)` or
   `submit_reward_pair(closer_to_food, further_from_food)`. Both
   arguments are required, at least one value must change, and every field outside
   the pair stays fixed. Invalid or duplicate calls retry the entire pair within
   the existing dialogue timeout and context bounds.
7. Both decision paths validate the complete configuration and permitted changes,
   recheck whether Snake Lab is busy, and reject duplicate configurations at the
   submission boundary. The trace records both selected values, selection source,
   validation, baseline and best-ever gold IDs, and confirmed submission run ID.

Selection logs include used and completed choices, legal and remaining counts,
and eligibility. `selection_exhausted` means all permitted dimension changes from
that baseline are used. It does not mean every schema combination has been tested.
The loop marks that baseline as a local dead end and tries the previous gold.

Previous golds are strict record highs reconstructed in completion order from
completed runs; tied scores and non-gold runs are not backtracking targets.
Best-ever gold stays unchanged until beaten. The active baseline stays in use
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
parameters. The schema remains the source of legal-value rules.

Reward-pair deployment is planned as an uninstall/install of both Snake Lab and
Fr3d, starting with fresh data. This implementation adds no data migration or
automatic deletion of experiment history.
