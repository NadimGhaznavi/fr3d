# Release 0.21.0 — Round-Robin Search and Continuous Numeric Ranges

Status: source implementation complete; 281 Fr3d tests and 16 Snake Lab
configuration tests pass. Clean reinstall and live-run verification remain.

This release expands the Snake Lab configuration ranges, makes learning rate, gamma, and epsilon
continuous, replaces dimension ranking with round-robin selection, and reduces
Fr3d validation to types, bounds, and submission structure.

- The new JSON spec will be installed in Snake Lab in conjunction with this release.
- Snake Lab will be uninstalled, the DB dropped, and then it will be reinstalled.
- Fr3d will also be uninstalled, then reinstalled.
- Historical-data migration is out of scope.

# Choosing the Next Parameter

Replace the current least-explored parameter selection and random tie-breaking
with a simple round-robin cycle. Use this fixed order, then repeat:

1. `model.hidden_size`
2. `training.sequence_length`
3. `training.batch_size`
4. `training.learning_rate`
5. `training.gamma`
6. `epsilon_pair`
7. `reward_pair`

Perform the existing exchange for the selected dimension, then move to the next.
Keep the cycle position in memory and start at the beginning after a service
restart. Gold promotion and backtracking do not reset the cycle. No persistent
scheduling history or new retry or recovery flow is required. Existing experiment
waiting, retries, duplicate checks, and failure handling remain intact. Local
validation is reduced to the checks described below.

Each epsilon or reward pair occupies one turn, including an automatic submission
when only one eligible pair remains in a finite grid. Continuous epsilon pairs
always use the existing pair conversation. Preserve the existing pair conversations,
reports and atomic value selection, with the reduced local validation below.

Skip finite dimensions with no unused candidates in their planned schema-derived
grid at the active baseline. Preserve history matching outside the selected
dimension. Learning rate, gamma, and epsilon are continuous and have no finite
grid or remaining-choice count; keep them eligible rather than declaring them
exhausted from recorded history.
Continue rejecting duplicate configurations.

Retain existing gold backtracking and stopping behavior if all dimensions are
exhausted, although the continuous dimensions means grid exhaustion
alone will not trigger that condition under v2. Round-robin does not guarantee
exploration of every configuration.

Retain Fr3d's existing fixed seed of `1970`. `training.learning_rate` accepts any
finite number from `0.0005` through `0.0050`, inclusive, with default `0.0021`.
There is no required step or rounding to a grid. The configuration space is no
longer a finite schema-defined grid, so the previous total combination counts no
longer apply. The planned dimensions are:

| Dimension | Intended values | Grid size |
| --- | --- | --- |
| `model.hidden_size` | 64–512, step 32 | 15 |
| `training.sequence_length` | 4–64, step 4 | 16 |
| `training.batch_size` | 8–128, step 8 | 16 |
| `training.learning_rate` | 0.0005–0.0050, continuous | Not enumerated |
| `training.gamma` | 0.90–0.99, continuous | Not enumerated |
| `epsilon_pair` | Initial 0.85–0.99 and decay 0.90–0.99, continuous | Not enumerated |
| `reward_pair` | Closer 0–6 and further −6–0, integer steps | 49 |

Finite pair counts include the baseline combination when it is on the grid. Recorded
combinations, including that baseline, are excluded from unused choices.

# Validation Responsibility

Fr3d asks: **Are the submitted values of the correct type and within reasonable
bounds?** Snake Lab decides whether the complete configuration is valid and can
execute.

- Check numeric types and the schema's minimum/maximum bounds, including exclusive
  bounds where specified. Reject booleans as numbers, numeric strings, fractional
  values for integer fields, and non-finite values such as NaN and infinity.
- Keep the submission shape checks: required arguments, no unexpected fields, and
  both pair values supplied together. Construct candidates from the active
  baseline so only the selected dimension changes. Preserve fixed fields,
  unchanged-candidate rejection, and duplicate checks as search behavior.
- Do not enforce `multipleOf`, enum membership, or full-schema and cross-field
  validity locally. Apply the same reduced checks to LLM proposals, automatic
  pair selections, and the startup configuration. LLM tool argument schemas must
  also reflect this reduced validation scope.
- For finite dimensions, continue using the schema's steps and value sets to
  describe the intended search grid in prompts, reports, and availability tracking.
  These guide selection; they are not a local submission whitelist. A correctly
  typed, in-bounds value
  outside that grid can reach Snake Lab for its decision.
- Enumerate the remaining finite grids without full-schema filtering. Decimal
  fields have no steps; do not add custom decimal validators or artificial grids.
  Count recorded grid values when assessing grid
  exhaustion; an off-grid recorded value must not consume a different grid value.
  Pair reports describe planned combinations, not server-certified valid configs.
- Treat local checks passing as ready for submission, not as server acceptance.
  Only an accepted Snake Lab response with a run ID establishes a submitted
  experiment. Surface server rejection details through the existing error flow;
  rejection does not consume a grid choice or establish an experiment. No new
  retry or recovery mechanism is introduced by this release.

For example, Fr3d should pass `0.94` for gamma and the learning-rate default
`0.0021` through its local checks. It should reject gamma `5`, a numeric field
containing `"hello"`, or a fractional batch size. Learning rate, gamma, and both
epsilon values have no step constraints in v2. Snake Lab uses its standard schema
validator to decide whether the complete config is valid.

# Implementation Plan

- Install the same v2 schema on both systems, give it the v2 identity, and update
  `SCHEMA_PATH` in `fr3d/app/whole_config/configuration.py`, the schema check in
  `scripts/install.py`, and the v2 file's `$id`.
  Snake Lab owns full config validation.
- Replace the current completed-choice ranking and random tie-breaking with the
  round-robin cycle described above. Preserve the existing unknown availability
  counts for continuous learning rate, gamma, and epsilon.
- Validate against a reduced schema containing types, bounds, and required
  submission structure, plus an explicit finite-number check. Use this scope for
  startup, LLM tool arguments, candidate checks, and automatic pair submissions.
  Keep fixed-field preservation and duplicate checks as search behavior.
- Remove `multipleOf` from gamma and both epsilon fields, as already done for
  learning rate. Use standard server validation; remove the custom decimal-step
  validator. Keep integer steps for model size, sequence length, and batch size.
- Preserve atomic pair submissions. Show continuous epsilon history as recorded
  pairs with run IDs, statuses, scores, and baseline identification, without an
  invented grid. Keep the reward grid and its zero/one/many unused-pair behavior.
  Do not enumerate any continuous dimension or the full configuration product.
- Update selector tests, prompts, reports, and documentation to reflect these rules.
- Verify Snake Lab acceptance and rejection handling using the acceptance checks
  below. Address any server-side validation defects in Snake Lab.

# Acceptance Checks

- The selector follows the documented order and wraps around. Each pair uses one
  turn; exhausted finite dimensions are skipped.
- Restart begins the cycle again. Gold promotion and backtracking do not reset it.
  Existing waiting, retries, and failure handling are preserved.
- Learning rate accepts both inclusive bounds, `0.0021`, and values between the
  former steps, such as `0.002123456`. It has no finite remaining-choice count and
  stays eligible after previous learning-rate experiments. Gamma and both epsilon
  values also accept values between their former steps and remain eligible.
- Local validation rejects bad types, booleans in numeric fields, non-finite
  numbers, fractional integer values, out-of-bounds values, and malformed calls.
  It passes in-bounds off-grid proposals to Snake Lab without enforcing steps.
- Finite-grid counts match the table above. Gamma and epsilon accept `0.94` and
  `0.94321` with standard server validation. Recorded off-grid integer values do
  not reduce unused grid counts.
- Epsilon reports show recorded pairs and bounds, and always use the LLM for a
  new pair. Reward reports cover 49 combinations: zero unused pairs skip the
  dimension, one bypasses the LLM, and multiple use the existing conversation.
  Both values are submitted together; other dimensions remain fixed.
- Snake Lab rejection details reach Fr3d's existing error flow without a false
  submission record or consumption of a grid choice. Acceptance is established
  only by the server's accepted response and run ID.
- A fresh installation submits and completes the v2 default configuration, with
  no historical-data migration. Verify actual server acceptance of the intended
  decimal values as well as local validation.

# Deployment Status

Both source checkouts now use the same v2 schema. Snake Lab uses the standard
JSON Schema validator with no custom decimal-step implementation. Runtime services
have not been reinstalled or started as part of this release work.

Deployment will be performed by the user. The remaining deployment checks are the
clean reinstall of both services, installation of the matching v2 schema, and
submission and completion of the first live experiment.

# Gaps

None outstanding in the requirements. Implementation and verification work is
listed above.
