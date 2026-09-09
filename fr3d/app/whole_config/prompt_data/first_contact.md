# First comparison for the selected parameter

Snake Lab trains an agent to play Snake. Choose a first alternative value for the parameter named in the report. No completed alternative has been tested with the other settings in current gold.

The objective is the highest episode score over the complete simulation. Only the selected parameter changes; all other settings are copied from gold. Use the supplied configuration, parameter constraints, and gold result to propose a useful comparison.

When present, `untested_grid_values` lists the remaining planned grid values after excluding all previously submitted configurations matching the other gold settings, including seed, regardless of run status. Use this list as guidance to choose an untested value.

Call `submit_parameter` with only `value`, using the specified numeric type and bounds. The value must be finite and produce a configuration that has not already been submitted. A prose answer does not submit a value.
