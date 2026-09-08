# Sample Prompt

# Task: Explore Epsilon Exploration Parameters (2D)

You are optimizing the hyperparameters for a Reinforcement Learning Snake agent. 
Your goal is to maximize the high_score by selecting the best combination of `epsilon.initial` and `epsilon.decay`.

## Current State
- **Active Search Baseline (Current Gold):** `initial: 0.96`, `decay: 0.97` (High Score: 48)
- **Historical Best (Best Gold):** `initial: 0.96`, `decay: 0.97` (High Score: 48)

## The Search Space
You must choose a combination of `initial` and `decay`. 
Valid options for `initial`: [0.91, 0.96, 0.99]
Valid options for `decay`: [0.95, 0.97, 0.99]
*(Note: `epsilon.minimum` is fixed at 0.0 and cannot be changed).*

## Historical Performance Heatmap
Below is a table of high scores achieved for different combinations. "N/A" means the combination has not been tested yet.

| initial \ decay | 0.95 | 0.97 | 0.99 |
| :--- | :---: | :---: | :---: |
| **0.91** | 32 | 35 | N/A |
| **0.96** | 41 | **48** | N/A |
| **0.99** | N/A | 42 | N/A |

## Instructions
1. Analyze the heatmap. Look for trends (e.g., does a higher initial value help? does a slower decay help?).
2. Identify all combinations marked as **N/A**.
3. Select exactly ONE untested combination that you believe will yield the highest score.
4. You MUST NOT select a combination that has already been tested.
5. Submit your choice using the `submit_epsilon_pair` tool.

## Search Context
The "Current Gold" is the active baseline. You are changing BOTH `initial` and `decay` simultaneously from this baseline. Use the heatmap to guide your reasoning.