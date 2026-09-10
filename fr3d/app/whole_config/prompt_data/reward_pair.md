# Explore the Food-Distance Reward Pair

Choose the combination of `game.rewards.closer_to_food` and `game.rewards.further_from_food` most likely to improve the Snake agent's high score. Consider their combined effect using the JSON report of matching experiments below. Use the results to assess the balance between rewarding movement toward food and penalizing movement away; do not assume symmetric rewards are best.

The report's `gold` is the active search baseline. If `best_gold` is present, it is the best-ever result and may differ from that baseline. Every record in `experiments` matches the current seed and all other baseline configuration fields outside the reward pair. All other settings, including epsilon and other rewards, remain fixed at the active baseline.

Choose one unused pair from `value_results`, which lists every planned grid pair sorted numerically by `closer_to_food`, then `further_from_food`. Each entry's `results` contains matching current-seed run results or `UNTESTED`; choose a pair marked `UNTESTED`. Fr3d checks types and bounds; Snake Lab decides full configuration validity. The grid is guidance, not a local whitelist. Pairs in `experiments` have already been used and cannot be selected, regardless of status. Only completed experiments provide performance evidence. Missing scores are unavailable, not zero. Each experiment includes its run ID; match it to `gold.run_id` to identify the baseline.

When supplied, each `history` array contains high scores from completed runs with that entry's value or pair and every other gold setting matching except the seed. These runs use different seeds from current gold. Scores are sorted numerically from lowest to highest, retaining zero and repeated scores; `[]` means no qualifying history. Use these scores to guide selection. Historical scores do not mark a value or pair as tested on the current seed or change its eligibility.

Call `submit_reward_pair` with only `closer_to_food` and `further_from_food`. Supply both values together. At least one value must differ from the baseline; either value may remain unchanged. A prose answer does not submit a pair.
