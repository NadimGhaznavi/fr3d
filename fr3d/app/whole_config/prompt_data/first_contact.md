# First comparison for the selected parameter

Snake Lab trains an agent to play Snake. Choose a first alternative value for the parameter named in the report. No completed alternative has been tested with the other settings in current gold.

The objective is the highest episode score over the complete simulation. Only the selected parameter changes; all other settings are copied from gold. Use the supplied configuration, parameter constraints, and gold result to propose a useful comparison.

For fixed parameters, `value_results` lists every valid grid value in ascending numeric parameter order. Each entry contains its matching run results (high score, status, and baseline marker), or `UNTESTED` if never submitted with the other gold settings, including seed. Choose an entry marked `UNTESTED`. Failed, cancelled, queued, and running entries are already used; only completed results provide performance evidence. A null score is unavailable, not zero. Continuous parameters retain the completed `experiments` history.

Call `submit_parameter` with only `value`, using the specified numeric type and bounds. The value must be finite and produce a configuration that has not already been submitted. A prose answer does not submit a value.
