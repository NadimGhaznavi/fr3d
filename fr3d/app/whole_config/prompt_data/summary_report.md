# Explore the selected parameter

Snake Lab trains an agent to play Snake. Choose a new value for the parameter named in the report to achieve a higher maximum episode score over the complete simulation.

The report includes current gold and completed experiments matching gold on every other configuration value. Only the selected parameter changes. Use this comparable history to propose an untested configuration.

For fixed parameters, `value_results` lists every valid grid value in ascending numeric parameter order. Each entry contains its matching run results (high score, status, and baseline marker), or `UNTESTED` if never submitted with the other gold settings, including seed. Choose an entry marked `UNTESTED`. Failed, cancelled, queued, and running entries are already used; only completed results provide performance evidence. A null score is unavailable, not zero. Continuous parameters retain the completed `experiments` history.

Call `submit_parameter` with only `value`, using the supplied numeric type and bounds. The value must be finite. A prose answer does not submit a value.
