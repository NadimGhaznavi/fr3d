# Parameter selection

The search loop selects one parameter before building the LLM conversation report.
The conversation and its prompts do not select which parameter to explore.

1. `SearchStore.gold()` reads the best completed run from MariaDB, using maximum
   episode score and the existing completion-time and run-ID tie breakers.
2. `SearchStore.parameter_values()` queries each searchable parameter directly.
   SQL matches every other configuration column to gold, groups by the parameter
   value, and counts completed runs and the gold row. It does not read episode
   scores. All run statuses reserve values, as in the duplicate check.
3. `assess_parameters()` checks that gold is present and compares used values with
   the schema. `value_space.py` handles enums, integer ranges, and `multipleOf`
   with inclusive or exclusive bounds. Missing gold is an error, not exhaustion.
4. `choose_parameter()` keeps eligible parameters with the fewest distinct
   completed values, choosing randomly among ties.
5. Only then does `SearchReports.parameter_report()` fetch matching episode scores
   and build the existing report for the unchanged conversation.

The decision log records gold, used and completed values, legal and remaining
counts, and eligibility for every parameter. `selection_exhausted` means all
single-parameter changes from the active baseline are already used. It does not
mean every combination in the schema has been tested. The loop marks that
baseline as a local dead end and tries the previous gold.
Previous golds are strict record highs reconstructed in completion order from
completed runs; tied scores and non-gold runs are not backtracking targets.
Best-ever gold stays unchanged until beaten. The active baseline stays in use
across iterations, and a new best-ever gold becomes the active baseline.
Dead-end flags are held for the process lifetime and logged; after restart they
are recomputed from database history. Once all previous golds are exhausted,
the loop waits until stopped. It does not explore non-gold baselines.

During backtracking the existing report `gold` field holds the active baseline
used by candidate construction. `best_gold` and `search_context` identify the
best-ever result separately. Conversation code and prompts are unchanged.

`SearchStore` owns the direct database connection and SQL. `SearchReports` extends
it with the score history and report builder; no HTTP report server participates
in selection. SQL identifiers come from the bundled schema and values are bound
parameters. The schema remains the source of legal-value rules.
