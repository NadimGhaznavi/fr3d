# Explore the Epsilon Pair

Choose the combination of `epsilon.initial` and `epsilon.decay` most likely to improve the Snake agent's high score. Consider their combined effect using the table of matching experiments below.

The report's `gold` is the active search baseline. If `best_gold` is present, it is the best-ever result and may differ from that baseline. Every table result matches all baseline configuration fields outside the epsilon pair. All other settings, including `epsilon.minimum`, remain fixed at the active baseline.

Choose one unused pair within the supplied bounds. Continuous values have no step or rounding requirement; the table shows recorded pairs, not a grid of all possibilities. If a finite grid is supplied, use it as guidance. Fr3d checks types and bounds; Snake Lab decides full configuration validity. `Untested` means no recorded experiment; status labels are used combinations and cannot be selected. Only completed experiments provide performance evidence. Missing scores are unavailable, not zero. When a cell contains multiple runs, each result is labeled by run ID.

Call `submit_epsilon_pair` with only `initial` and `decay`. Supply both values together. At least one value must differ from the baseline; either value may remain unchanged. A prose answer does not submit a pair.
