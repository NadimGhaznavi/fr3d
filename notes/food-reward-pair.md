# Food-Distance Reward Pair

Extend the epsilon pair behavior to `game.rewards.closer_to_food` and
`game.rewards.further_from_food`. Deployment will use a clean uninstall/install
of both Snake Lab and Fr3d. No data migration is included.

## Requirements

- Replace individual selection of these two reward fields with one `reward_pair`
  search dimension. Keep the epsilon pair and remaining individual dimensions.
- Derive legal values from the schema, including bounds and `multipleOf`. The
  current grid has closer-to-food values `[0, 2, 4]` and further-from-food values
  `[-4, -2, 0]`, for nine combinations.
- Require finite enumerable value sets. Retain fixed fields in the pair and
  reject unsupported schemas clearly during configuration loading.
- Count distinct completed pairs when selecting the least-explored eligible
  dimension, preserving the existing tie-breaking policy.
- Match history against the active baseline in every field outside the selected
  pair. Reward-pair history therefore holds both epsilon fields fixed, and
  epsilon-pair history holds both reward fields fixed.
- A recorded experiment reserves its complete configuration regardless of status.
  Only completed experiments supply performance evidence. An LLM proposal alone
  does not reserve a configuration.
- Provide a table with closer-to-food rows and further-from-food columns. Show
  completed high scores, `Untested` for unused cells, and status for used cells
  without scores. Label multiple results with their run IDs. Identify the active
  baseline and distinguish it from best-ever gold during backtracking.
- With multiple eligible pairs, use a dedicated prompt and
  `submit_reward_pair(closer_to_food, further_from_food)`. Require both arguments,
  reject extra fields, and apply schema validation to the complete candidate.
- Either value may remain unchanged, but at least one must differ from the active
  baseline. Apply both selected values atomically; leave every other field fixed.
- Retry the entire pair after invalid or duplicate proposals, using the existing
  dialogue timeout and context limits. Retain no partial choice from a rejection.
- With one eligible pair, construct and submit it directly without the LLM.
  Apply the same configuration, change-boundary, busy-state, and duplicate checks.
- With no eligible pairs, skip this dimension for that baseline. Preserve existing
  gold backtracking and stopping behavior when all its dimensions are exhausted.
- Record both reward values, automatic or LLM selection, validation outcome,
  active baseline, best-ever gold, and confirmed submission run ID.

## Validation

Cover schema-derived combinations and integer normalization, atomic validation,
matching history with the other pair fixed, report cells, pair-specific retries,
sole-candidate submission, duplicate rejection, and exhaustion/backtracking.
Run epsilon and individual-parameter regression tests alongside the reward tests.
