# Experiment

Snake Lab trains a reinforcement-learning agent to play Snake.

The objective is to achieve the highest game score possible.
High score is the measure of success for this project, not mean or median score.

The neural network is trained using reinforcement learning.
The experiment configuration contains parameters that affect learning.

For this experiment, you may change only:

- learning_rate

All other configuration parameters, including the seed, are fixed.

## Previous Experiments

### Configuration

| Run | Learning Rate |
|---|---:|
| 101 | 0.001 |
| 102 | 0.002 |
| 103 | 0.004 |

### Score

| Run | Mean Score | Median Score | High Score |
|---|---:|---:|---:|
| 101 | ... | ... | ... |
| 102 | ... | ... | ... |
| 103 | ... | ... | ... |

### Highscores

Each run's table shows the first epoch, each new cumulative high score, and the
final epoch (once, even if it sets a new high score). Loss is the recorded loss at
that epoch. Loss Change is current loss minus the previous displayed row's loss
within the same run; negative means a decrease. Missing losses and changes with
a missing endpoint are N/A. The first row's change is N/A.

#### Run 101

| Epoch | Highscore | Loss | Loss Change |
|---:|---:|---:|---:|
| ... | ... | ... | ... |

#### Run 102

| Epoch | Highscore | Loss | Loss Change |
|---:|---:|---:|---:|
| ... | ... | ... | ... |

#### Run 103

| Epoch | Highscore | Loss | Loss Change |
|---:|---:|---:|---:|
| ... | ... | ... | ... |

### Training

| Run | Mean Loss | Final Loss |
|---|---:|---:|
| 101 | ... | ... |
| 102 | ... | ... |
| 103 | ... | ... |

### Duration

Duration is elapsed seconds from start to completion, excluding queue time and including pauses.
N/A means timestamps are missing or completion precedes start.

| Run | Duration (s) |
|---|---:|
| 101 | ... |
| 102 | ... |
| 103 | ... |

## Task

Choose the learning rate for the next experiment.

Use the experimental results above as evidence, prioritizing high scores and
their progression across epochs.

## Optional Historical Report

Before choosing, you may call `view_best_worst_report` with no arguments once
to inspect the top and bottom ten completed simulations, including learning rates
and durations. Historical runs may have different versions and settings; use
them as context alongside the comparable runs above. Then submit your learning rate.

## Response Tool

Submit your proposed learning rate through the `submit_learning_rate` function tool, using the numeric argument `learning_rate`.
Supply only `learning_rate`, a number greater than zero and at most one.
Fr3d validates the value and starts the next experiment.

Respond through the tool, not with a markdown or free-text proposal.
