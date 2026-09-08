# Pre-Release 0.20.0 — Epsilon Pair Search

Status: agreed requirements for implementation of release 0.20.0.

## Purpose

Fr3d currently asks the LLM to choose one configuration value per exploration dialogue. This release introduces a coupled decision for `epsilon.initial` and `epsilon.decay` so the LLM can consider their combined effect on high score.

When multiple eligible pairs remain, the LLM receives a dedicated report and prompt, then submits both values through one tool call. When exactly one eligible pair remains, Fr3d selects it directly. In either case, Fr3d applies the pair to the active search baseline and submits the resulting experiment to Snake Lab.

## Scope

This release covers epsilon pair selection, search-space tracking, reporting, prompting, tool validation, candidate construction, and decision history.

The epsilon pair replaces the two individual epsilon search dimensions. All other searchable parameters remain individually selectable. Additional parameter groups and automatic selection for individual parameters are outside this release's scope.

## Terms

- **Epsilon pair:** the ordered values `(epsilon.initial, epsilon.decay)`.
- **Active search baseline:** the configuration from which the next candidate is constructed. The existing search can backtrack to an earlier gold configuration.
- **Best-ever gold:** the highest-scoring configuration retained by the search. It may differ from the active baseline.
- **Pair decision:** a selection of both epsilon values together, made by the LLM or directly by Fr3d when only one eligible pair remains.
- **Used pair:** a pair with a recorded experiment matching the active baseline in every field outside the pair.
- **Completed pair:** a used pair with a completed experiment supplying performance evidence.
- **Eligible pair:** an unused pair that produces a schema-valid configuration and changes at least one epsilon value from the active baseline.

## Core Requirements

### Clean Start and Data Migration

The system will be wiped for this release and start with fresh data. Migrating data from earlier releases is out of scope. The implementation can assume there is no prior experiment or search history to carry forward.

### Search Selection

Treat the epsilon pair as one search dimension. Preserve the existing preference for eligible dimensions with the fewest completed choices, counting distinct completed pairs for epsilon. Preserve the existing tie-breaking behavior.

### Search-Space Tracking and History

Track used and completed pairs separately. An independently explored initial or decay value does not establish that a particular pair has been explored.

For independently allowed value sets containing N initial values and M decay values, the pair has N × M possible combinations. Complete configurations must still pass schema validation.

For example, these are distinct pairs:

| `epsilon.initial` | `epsilon.decay` |
| --- | --- |
| 0.96 | 0.97 |
| 0.96 | 0.95 |
| 0.91 | 0.97 |

Match every configuration field outside the epsilon pair to the active baseline when assessing history. The same pair at a different learning rate does not consume a combination for this baseline.

An LLM proposal alone consumes nothing. A recorded experiment blocks duplicate submission; only completed experiments provide performance evidence. Preserve existing failure handling for queued, running, failed, cancelled, and otherwise unfinished experiments.

### Candidate Availability and Exhaustion

After selecting the epsilon dimension, determine the number of eligible pairs:

| Eligible pairs | Behavior |
| --- | --- |
| 0 | Mark the pair dimension exhausted for this baseline and skip it. |
| 1 | Construct, validate, and submit the sole candidate directly, without calling the LLM. |
| 2 or more | Ask the LLM to select one eligible pair. |

If every dimension at the active baseline is exhausted, use the existing gold backtracking and stopping behavior. Exhausting one pair grid does not mean the full configuration space is exhausted. In a valid 3 × 3 grid, the existing baseline occupies one of the nine combinations.

### Schema Constraints

Derive allowed values from the configuration schema. Retain the pair when one epsilon field is fixed or has only one legal value; require that value in pair submissions. If no eligible combinations remain, the dimension is exhausted.

Require finite enumerable epsilon value sets. Report a clear configuration error for unsupported schemas; never treat an unsupported schema as an exhausted search dimension.

### Candidate Construction and Gold Interaction

Both epsilon values must be supplied, and at least one must differ from the active baseline. From `(0.96, 0.97)`, allow `(0.96, 0.99)` as well as `(0.99, 0.99)`, subject to eligibility. Reject the unchanged baseline pair.

For either an LLM selection or an automatic selection:

1. Copy the active search baseline configuration.
2. Replace `epsilon.initial` with the selected initial value.
3. Replace `epsilon.decay` with the selected decay value.
4. Leave all other configuration fields unchanged, including `epsilon.minimum`.
5. Validate the complete configuration and recheck candidate eligibility before submission.
6. Submit the completed configuration to Snake Lab.

Both epsilon values must originate from the same pair decision. Never combine values from separate decisions. An incomplete or invalid pair must not partially update or submit a candidate.

### Epsilon Pair Report

Provide the LLM with a table whose rows are allowed initial values and whose columns are allowed decay values. Derive the axes from the schema. Each completed cell shows the high score for the matching configuration; an unused cell shows `Untested`. Used combinations without a completed score must be distinguishable from untested combinations.

The report must identify the active baseline pair and score and make clear when best-ever gold differs from it. Every result in the table must match the active baseline in all configuration fields outside the epsilon pair.

The current schema provides initial values `[0.91, 0.96, 0.99]` and decay values `[0.95, 0.97, 0.99]`, giving nine combinations. For an illustrative active baseline of `(0.91, 0.99)` with high score 33 and no other matching experiments:

| Initial / Decay | 0.95 | 0.97 | 0.99 |
| --- | --- | --- | --- |
| 0.91 | Untested | Untested | **33 (baseline)** |
| 0.96 | Untested | Untested | Untested |
| 0.99 | Untested | Untested | Untested |

For used cells without completed scores, show the experiment status (`Queued`, `Running`, `Failed`, or `Cancelled`). A completed experiment with no score is labeled `Completed (score unavailable)`. Reserve `Untested` for cells with no recorded experiment.

The database enforces configuration uniqueness within a Snake Lab version, but the same configuration can exist across versions. If multiple runs occupy a cell, list their results or statuses with run IDs rather than aggregating scores. Only completed runs provide performance evidence.

### Dedicated LLM Prompt

When multiple eligible pairs remain, the prompt must explain the high-score objective, identify both parameters, provide their allowed values and the pair report, and request exactly one eligible pair through `submit_epsilon_pair`.

State that both values must be supplied, at least one must change, and all other fields remain fixed at the active baseline. The prompt's eligibility instructions must agree with the rules enforced by the tool and submission boundary.

### Submission Tool and Retries

Use `submit_epsilon_pair` with required arguments `initial` and `decay`. Reject missing arguments and extra fields. Derive value constraints from the corresponding configuration-schema fields and validate the resulting complete configuration before submission.

Reject illegal values and duplicate or unchanged candidates. Reuse the existing bounded retry policy, with feedback specific to the rejected pair. Retry the entire pair decision without retaining one value from a rejected call.

The automatic selection path must enforce the same candidate validation and duplicate checks without an LLM tool call.

### Decision History

Record the selected pair dimension, both selected values, active baseline, best-ever gold, validation outcome, and submitted run ID where available. Record whether the pair was selected by the LLM or automatically by Fr3d so that automatic submissions remain explainable without a dialogue.

## Acceptance Checks

- Fresh-data startup requires no migration of experiment or search history.
- The selector treats epsilon as one pair dimension and preserves selection behavior for other parameters.
- Both values are supplied atomically; incomplete pairs are rejected.
- Either or both epsilon values may change, but an unchanged pair is rejected and other fields remain fixed.
- History matches the active baseline in every field outside the pair.
- Recorded experiments block duplicates; only completed experiments provide scores and count as completed choices.
- Zero eligible pairs exhaust the dimension; one eligible pair bypasses the LLM; multiple eligible pairs use the dedicated prompt and tool.
- Pair exhaustion preserves existing backtracking and stopping behavior and is distinguished from global exhaustion.
- Reports show all schema-derived combinations and distinguish untested cells from used cells without scores.
- Tool validation and retries apply to the entire pair; automatic selections receive equivalent candidate checks.
- A fixed epsilon field remains part of the pair with its required value.
- Non-enumerable epsilon schemas fail clearly during configuration loading.
- Multiple results in a report cell retain their run IDs and individual scores or statuses.
- Decision history captures both values and whether selection was automatic or made by the LLM.
- Individual-parameter decisions continue to operate.

# Gaps

None outstanding.
