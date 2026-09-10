# Explore the selected parameter

The Snake Lab will run a *Reinforcement Learning* simulation using our configuration.

Your job is to choose a new value for the parameter named in the report and try to achieve a new high score!

- The report includes current gold and completed experiments matching gold on every other configuration value. 
- You can only change one parameter. 
- Use this comparable history to propose an untested configuration.

For fixed parameters, `value_results` lists every valid grid value in ascending numeric parameter order. Each entry's `results` contains matching current-seed run results (high score, status, and baseline marker), or `UNTESTED` if never submitted with the other gold settings, including seed. Choose an entry marked `UNTESTED`. Failed, cancelled, queued, and running entries are already used; only completed results provide performance evidence. A null score is unavailable, not zero.

For continuous parameters, `experiments` contains completed current-seed experiments. When supplied, `value_results` lists observed values from current-seed runs and qualifying historical runs, sorted numerically by value. It is not a finite grid. You may choose a value marked `UNTESTED` or propose a new, unlisted value within the supplied bounds, provided the resulting configuration has not already been submitted.

When supplied, each `history` array contains high scores from completed runs with that entry's value or pair and every other gold setting matching except the seed. These runs use different seeds from current gold. Scores are sorted numerically from lowest to highest, retaining zero and repeated scores; `[]` means no qualifying history. Use these scores to guide selection. Historical scores do not mark a value or pair as tested on the current seed or change its eligibility.

Call `submit_parameter` with only `value`, using the supplied numeric type and bounds. The value must be finite. A prose answer does not submit a value.
