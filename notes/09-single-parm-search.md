# Coordinate Descent

Your system is currently doing Coordinate Descent (tweaking one parameter at a time). Let’s count the number of valid options for each tunable parameter in your schema:
seed: 2 options (1970, 42)
game.rewards.closer_to_food: 3 options (0, 2, 4)
game.rewards.further_from_food: 3 options (-4, -2, 0)
model.hidden_size: 2 options (224, 256)
training.sequence_length: 4 options (4, 8, 16, 32)
training.batch_size: 3 options (8, 24, 48)
training.learning_rate: 3 options (0.0020, 0.0021, 0.0022)
epsilon.initial: 3 options (0.91, 0.96, 0.99)
epsilon.decay: 3 options (0.95, 0.97, 0.99)
Total single-parameter neighbors to check = 23.
If the system found the "48" config, it then had to check up to ~22 other single-parameter variations to prove it was a local optimum. If it hit dead ends, it backtracked, found another branch, climbed to 48 again, and checked another ~22 neighbors.
83 simulations ÷ 23 neighbors ≈ 3.6 major search nodes explored.
This perfectly matches your earlier timeline: It climbed, hit a dead end at 44, backtracked, and climbed to 48. It has now thoroughly mapped the immediate 1-step neighborhood of the best configs it can find.