# Parameter Grouping

## 1. The Optimizer Dynamics

**Parameters**

- `training.batch_size`
- `training.learning_rate`

**Search Space:** 3 × 3 = 9 combinations

**Why:** Highly Coupled. Larger batches give more stable gradient estimates, which often allows for (or requires) a higher learning rate. Smaller batches have high variance and need smaller LRs to prevent divergence. The LLM can easily spot if a high LR only works when the batch size is 48.

## 2. The Exploration Schedule

**Parameters**

- `epsilon.initial`
- `epsilon.decay`

**Search Space:** 3 × 3 = 9 combinations

**Why:** Highly Coupled. These two define the exact shape of the exploration curve. A high initial (0.99) with a fast decay (0.95) drops off a cliff. A high initial (0.99) with a slow decay (0.99) stays random for too long. The LLM needs to balance how much it explores with how long it explores.

## 3. The Reward Gravity

Implementation requirements: [Food-distance reward pair](food-reward-pair.md).

**Parameters**

- `game.rewards.closer_to_food`
- `game.rewards.further_from_food`

**Search Space:** 3 × 3 = 9 combinations

**Why:** Highly Coupled. This defines the "magnetic pull" of the food. If you reward moving closer by `4`, you usually want to penalize moving away by `-2` or `-4`. If you reward closer by `2` but penalize further by `0` (which your current Gold does!), the LLM needs to see if that asymmetry is actually optimal, or if a symmetric pull works better.

## 4. The Temporal Context

**Parameters**

- `training.sequence_length`
- `training.batch_size`

**Search Space:** 4 × 3 = 12 combinations

**Why:** Moderately Coupled. Both dictate how much "history" the RNN sees per update. Longer sequences mean the RNN has to remember further back. If the sequence is too long, a smaller batch size might be needed to keep the gradient updates stable, or vice versa.

> **Note:** 12 combinations is a slightly larger grid for a 3.5B model to parse, so save this for later.

## 5. Model Capacity vs. Stability

**Parameters**

- `model.hidden_size`
- `training.learning_rate`

**Search Space:** 2 × 3 = 6 combinations

**Why:** Loosely Coupled. A larger model (256 neurons) has more parameters and might require a slightly different learning rate to converge smoothly compared to the smaller model (224). It's a small grid, making it very easy for the LLM to solve.
