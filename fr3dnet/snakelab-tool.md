# Snake Lab Tool

The Snake Lab Tool lets Fr3d view experiment reports and choose the next [Snake Lab](/snake-lab) learning rate.

## View Latest Report

Call view_latest_report through snakelab_tool with no arguments, including during web chat with Nadim. It returns JSON with the latest three completed, comparable runs, or explains why it is unavailable. The automated learning-rate comparison uses the same JSON format.

Viewing is read-only and needs no pending decision. The report's Task and Response Tool sections belong to the preview; reading them does not request a new experiment.

## View Best and Worst

Call view_best_worst_report through snakelab_tool with no arguments. It returns the top ten and bottom ten completed simulations by high score, with learning rates, versions, epoch counts, and durations. Ties use the lower run ID first. This read-only ranking covers all versions and configurations; they may not be directly comparable.

Both reports show elapsed duration in seconds from simulation start to completion, excluding queue time and including pauses. The best/worst report has top_10 and bottom_10 lists; the comparison has a runs list. Missing numeric values are null. The ranking lists can overlap when scores tie or there are fewer than twenty runs.

During an automated learning-rate decision, you may call view_best_worst_report once before proposing a rate. Read the returned ranking, then call submit_learning_rate. If the lookup fails, use the comparison report already provided.

## Submit Learning Rate

When given an experiment report and asked for the next learning rate, call submit_learning_rate through snakelab_tool. Supply only learning_rate, a number greater than zero and at most one. All other configuration settings stay fixed.

Use the report's high scores and their progression to guide your choice. Each reported epoch also includes its loss and the loss change since the previous reported epoch. Negative change means loss decreased; null means unavailable. The final epoch is always included.

## Output

A successful submission returns the learning rate and new run ID. If the configuration has already completed on the same project version, the tool returns already_run and its report. Use those results to choose a different rate.

Submitting a learning rate requires a pending experiment decision. It cannot start arbitrary experiments during web chat.

- [Return to the Knowledge Base](/)
