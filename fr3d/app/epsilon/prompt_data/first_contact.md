# Choose a New Epsilon Decay

Snake Lab trains a reinforcement-learning agent to play Snake. We are beginning to tune epsilon decay.

There are many completed experiments available, but all of them used the same epsilon decay value: `0.97`. These experiments provide a baseline for comparison, but they do not yet show how changing epsilon decay affects performance.

Choose a new epsilon decay value that will provide a useful first comparison against the existing `0.97` baseline. High score is the objective. Only epsilon decay changes; all other experiment settings remain fixed.

Choose a value that is only a little different, higher or lower.

Submit your choice using `submit_epsilon_decay`. Supply only `epsilon_decay`, a finite number greater than zero and at most one. Do not submit `0.97`, because that value has already been extensively tested. A prose answer does not submit an epsilon decay. Report data is JSON; null means unavailable, not zero.