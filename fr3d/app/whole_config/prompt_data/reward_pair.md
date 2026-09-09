# Explore the Food-Distance Reward Pair

Choose the combination of `game.rewards.closer_to_food` and `game.rewards.further_from_food` most likely to improve the Snake agent's high score. Consider their combined effect using the JSON report of matching experiments below. Use the results to assess the balance between rewarding movement toward food and penalizing movement away; do not assume symmetric rewards are best.

The report's `gold` is the active search baseline. If `best_gold` is present, it is the best-ever result and may differ from that baseline. Every experiment record matches all baseline configuration fields outside the reward pair. All other settings, including epsilon and other rewards, remain fixed at the active baseline.

Choose one unused pair, using `eligible_pairs` as the planned search grid. Fr3d checks types and bounds; Snake Lab decides full configuration validity. The grid is guidance, not a local whitelist. Pairs in `experiments` have already been used and cannot be selected, regardless of status. Only completed experiments provide performance evidence. Missing scores are unavailable, not zero. Each experiment includes its run ID; match it to `gold.run_id` to identify the baseline.

Call `submit_reward_pair` with only `closer_to_food` and `further_from_food`. Supply both values together. At least one value must differ from the baseline; either value may remain unchanged. A prose answer does not submit a pair.
