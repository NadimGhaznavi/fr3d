# Explore the Epsilon Pair

Choose the combination of `epsilon.initial` and `epsilon.decay` most likely to improve the Snake agent's high score. Consider their combined effect using the JSON report of matching experiments below.

The report's `gold` is the active search baseline. If `best_gold` is present, it is the best-ever result and may differ from that baseline. Every experiment record matches all baseline configuration fields outside the epsilon pair. All other settings, including `epsilon.minimum`, remain fixed at the active baseline.

Choose one unused pair within the supplied bounds. Continuous values have no step or rounding requirement; the `experiments` array contains recorded pairs, not a grid of all possibilities. If `untested_grid_values` is supplied, use these remaining finite grid pairs as guidance. Fr3d checks types and bounds; Snake Lab decides full configuration validity. Pairs in `experiments` have already been used and cannot be selected, regardless of status. Only completed experiments provide performance evidence. Missing scores are unavailable, not zero. Each experiment includes its run ID; match it to `gold.run_id` to identify the baseline.

Call `submit_epsilon_pair` with only `initial` and `decay`. Supply both values together. At least one value must differ from the baseline; either value may remain unchanged. A prose answer does not submit a pair.
