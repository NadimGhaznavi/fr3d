# Objective

Summarize broader historical epsilon evidence for the LLM while preserving
comparability, useful coverage, and full history in saved reports.

# Implemented design

Saved epsilon reports retain `epsilon_pair_history` and add
`epsilon_pair_summary`. Model requests include the summary and omit the raw
broader history. Existing experiments, value results, and eligibility stay intact.

Group completed runs with available episode high scores by epsilon initial,
epsilon decay, and every other configuration field except seed. Include zero
scores. Keep different background configurations separate and show their
differences from the active baseline.

Each group contains run count, seed count, mean, minimum, maximum, the mean of
seed means, and current-seed statistics. Performance ordering uses the mean of
seed means so seeds with repeated runs do not receive extra weight. Maximum
score remains supporting evidence. Show the current seed when present and up to
three other seeds in numeric order, with an omitted-seed count. All seeds still
contribute to aggregate statistics.

# Evidence selection

Select the union of these categories, with explicit selection reasons:

- Active gold pair under matching background settings, when scored history exists: 1.
- Nearest comparable alternatives: 3.
- Weakest performers among the nearest 12 comparable alternatives: 3.
- Strongest comparable alternatives: 3.
- Strongest groups under different background settings: 2.

Categories may overlap, so the result contains at most 12 groups. Totals expose
how many groups were omitted. Nearby poor results mean the weakest within the
local set, not necessarily results below gold or statistically worse outcomes.

Distance is Euclidean in initial/decay parameter space with equal scales. This
is explicitly a heuristic; schedule-based distance is deferred until the actual
execution semantics can be verified. Performance ties prefer more seeds, then
proximity, then numeric pair order and canonical background-setting JSON.
Locality ties use numeric pair order and canonical background-setting JSON.
Recency is not used. No division by the gold score is required.

# Scope and validation

The bound applies to the broader history supplement, not the entire prompt.
Full current-seed experiments and existing cross-seed value results remain.
Reward history is unchanged.

Regression coverage checks configuration separation, zero scores, per-seed
statistics, seed-balanced performance selection, poor-result coverage, group and
seed limits, deterministic output, raw-history retention, actual model payloads,
and existing epsilon/reward selection behavior.
