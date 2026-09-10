# First comparison for the selected parameter

Snake Lab trains an agent to play Snake. Choose a first alternative value for the parameter named in the report. No completed alternative has been tested with the other settings in current gold.

The objective is the highest episode score over the complete simulation. Only the selected parameter changes; all other settings are copied from gold. Use the supplied configuration, parameter constraints, and gold result to propose a useful comparison.

For fixed parameters, `value_results` lists every valid grid value in ascending numeric parameter order. Each entry's `results` contains matching current-seed run results (high score, status, and baseline marker), or `UNTESTED` if never submitted with the other gold settings, including seed. Choose an entry marked `UNTESTED`. Failed, cancelled, queued, and running entries are already used; only completed results provide performance evidence. A null score is unavailable, not zero.

For continuous parameters, `experiments` contains completed current-seed experiments. When supplied, `value_results` lists observed values from current-seed runs and qualifying historical runs, sorted numerically by value. It is not a finite grid. You may choose a value marked `UNTESTED` or propose a new, unlisted value within the supplied bounds, provided the resulting configuration has not already been submitted.

When supplied, each `history` array contains high scores from completed runs with that entry's value or pair and every other gold setting matching except the seed. These runs use different seeds from current gold. Scores are sorted numerically from lowest to highest, retaining zero and repeated scores; `[]` means no qualifying history. Use these scores to guide selection. Historical scores do not mark a value or pair as tested on the current seed or change its eligibility.

Call `submit_parameter` with only `value`, using the specified numeric type and bounds. The value must be finite and produce a configuration that has not already been submitted. A prose answer does not submit a value.
