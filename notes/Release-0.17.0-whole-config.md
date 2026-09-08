# Release v0.17.0 Spec

## Overview

The purpose of this release is to expand Fr3d from searching individual hard-coded hyperparameters into managing the complete Snake Lab configuration search process. In this context **Fr3d** is the systemd `fr3d-server`.

Fr3d will own the experiment lifecycle. It will determine which configuration parameter should be explored, query the Snake Lab database for the relevant experiment history, assign the LLM a narrowly scoped task to propose the next value for that parameter, validate the response, construct a complete simulation configuration, and submit it to Snake Lab.

Snake Lab remains responsible for executing simulations and storing simulation configurations and results.

## Initial State

A new search begins with an empty Snake Lab experiment database. Fr3d will detect this and send the baseline simulation configuration to the Snake Lab server for execution.

Fr3d will construct the complete baseline configuration from the defaults in `pages/snake-lab-schemas/simulation-config-v1.schema.json`, apply the fixed values listed below, and validate it before submission. The baseline becomes gold only after its simulation completes successfully.

On startup with an existing database, Fr3d will wait for any queued or running simulation to finish, then select gold from completed runs. Gold is the configuration with the highest score; ties are resolved by the earliest completion time, then the lowest simulation row ID. If no completed run is available at that point, Fr3d will raise an error.

Fr3d will allow only one outstanding simulation at a time and check that Snake Lab is idle again immediately before submission.

## Failures

This system is designed to be lean and focused. Unexpected errors will propagate and crash Fr3d. There is no crash recovery, automatic retry, submission reconciliation, or paused error state. The `fr3d-server` systemd unit will use `Restart=no`. If the system breaks, we identify the root cause and fix it.

A failed or cancelled simulation, an unconfirmed submission, or an LLM conversation failure or timeout is an error. Invalid or duplicate LLM proposals use the normal corrective conversations below.

## Duplicate Simulation Configuration Forbidden

Before submission, Fr3d will compare the complete validated configuration against all stored simulation configurations, including queued, running, completed, failed, and cancelled runs. Every submitted simulation must have a unique configuration; failed and cancelled configurations are not automatically retried.

Comparison is by configuration values, independent of JSON key order or formatting. Reusing a parameter value is allowed when another configuration value differs. Proposing the current gold value without changing the configuration is a duplicate.

## Evolution of the Configuration

The completed baseline will be designated as the current **gold standard**. Every subsequent configuration accepted by Fr3d will copy current gold and change exactly one selected searchable parameter.

The objective is **high score**, defined as the maximum episode score within a completed simulation. Only completed runs are eligible for gold. A candidate becomes gold only if its high score is strictly greater than current gold's high score. Ties and lower scores retain current gold.

Changing gold may cause a previously explored parameter to become unexplored under the new configuration (see "Parameter Selection" below).

Fr3d will archive the initial gold and each promotion in the append-only `/opt/fr3d/logs/gold.jsonl` file, recording the run ID, complete configuration, high score, and previous gold run ID, if any. Strict score improvement prevents cycles through earlier gold configurations. Selecting existing gold on startup is not a new promotion.

## Fixed Configuration Elements

The following configuration elements are fixed for the duration of a search and will not be selected for exploration:

* `seed`: 1970
* `epochs`: 1500
* `game.board_width`: 20
* `game.board_height`: 20
* `game.initial_snake_length`: 3

### Out of Scope

After the operator decides the search is complete, the system may be reset, the database emptied, and the process started again with a different seed. Resetting the search and changing seeds are out of scope. For this release the seed will be fixed.

## Searchable Configuration Elements

All other supported Snake Lab configuration values are candidates for exploration unless explicitly excluded by Fr3d.

These currently include:

| JSON name                        | Database column                  |
| -------------------------------- | -------------------------------- |
| `game.max_moves_multiplier`      | `game_max_moves_multiplier`      |
| `game.rewards.food`              | `game_rewards_food`              |
| `game.rewards.wall`              | `game_rewards_wall`              |
| `game.rewards.snake`             | `game_rewards_snake`             |
| `game.rewards.max_moves`         | `game_rewards_max_moves`         |
| `game.rewards.empty`             | `game_rewards_empty`             |
| `game.rewards.closer_to_food`    | `game_rewards_closer_to_food`    |
| `game.rewards.further_from_food` | `game_rewards_further_from_food` |
| `model.hidden_size`              | `model_hidden_size`              |
| `model.layers`                   | `model_layers`                   |
| `model.dropout`                  | `model_dropout`                  |
| `training.sequence_length`       | `training_sequence_length`       |
| `training.batch_size`            | `training_batch_size`            |
| `training.replay_max_frames`     | `training_replay_max_frames`     |
| `training.learning_rate`         | `training_learning_rate`         |
| `training.gamma`                 | `training_gamma`                 |
| `training.tau`                   | `training_tau`                   |
| `training.max_gradient_norm`     | `training_max_gradient_norm`     |
| `epsilon.initial`                | `epsilon_initial`                |
| `epsilon.minimum`                | `epsilon_minimum`                |
| `epsilon.decay`                  | `epsilon_decay`                  |

The complete Snake Lab schemas are in the project's `pages/snake-lab-schemas` directory.

## Configuration Validation

Fr3d will use the configuration schema to determine each parameter's type and permitted bounds, including exclusive bounds. The LLM will propose only the selected parameter's value. Fr3d will construct and validate the complete candidate against the schema and confirm that exactly the selected parameter changed and all fixed values remain intact. Snake Lab remains responsible for its own submission validation; a server rejection will raise an error and crash Fr3d.

## Parameter Selection

After selecting gold on startup, and after each successful run and any resulting gold promotion, Fr3d will select the next parameter.

For each searchable parameter, Fr3d will find completed simulations matching current gold on every other configuration value. It will count the distinct tested values of that parameter in this matching history, including the gold value. Fr3d will select the eligible parameter with the smallest count, choosing randomly among ties. These counts are recomputed against current gold rather than carried over from an earlier gold configuration.

Some parameters have a finite integer range, such as RNN layers. Fr3d will exclude a parameter when every permitted value would produce a configuration already present in the database. Exhaustion is relative to current gold and is reconsidered when gold changes. If no parameters remain eligible, Fr3d will wait for operator intervention.

## Conversations

The existing `fr3d/app/epsilon` code will guide implementation.

This code will be parameterized to search any listed parameter. Parameter-specific assumptions, including the fixed golden learning rate and epsilon-only duplicate checks, will be replaced by the rules in this specification.

## LLM Workflow is Unchanged

The four conversation types remain `first_contact`, `summary_report`, `no_reruns`, and `invalid_value`.

Use `first_contact` when no completed simulation matching current gold on every other parameter has tested an alternative value for the selected parameter. Otherwise use `summary_report`. This decision uses the same matching history as parameter selection, so a parameter may return to `first_contact` after gold changes.

Use `invalid_value` to correct a proposal that fails validation and `no_reruns` to correct a proposal whose complete configuration already exists. Corrections retain the selected parameter and gold configuration for that conversation.

The `first_contact` will use an `initial_conversation.py` based on `notes/06-initial-epsilon.md` from an earlier release. Both initial and summary prompts will identify the selected parameter, its permitted type and bounds, current gold configuration and high score, and the high-score objective.

## The Summary Report

The summary report will contain completed simulations matching current **gold standard** on every configuration value other than the selected parameter. It will include current gold as the comparison point and identify each simulation's run ID, selected parameter value, and high score. Runs with different values for other parameters will not be included.

## End State

There is no automatic declaration of an optimal configuration. Searching continues until an operator stops it, an error crashes Fr3d, or no parameters remain eligible.