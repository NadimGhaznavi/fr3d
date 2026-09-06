# Snake Lab Tool

The Snake Lab Tool lets Fr3d view experiment reports and choose the next [Snake Lab](/snake-lab) learning rate.

## View Latest Report

Call view_latest_report through snakelab_tool with no arguments, including during web chat with Nadim. It returns the current report from the latest three completed, comparable runs, or explains why it is unavailable.

Viewing is read-only and needs no pending decision. The report's Task and Response Tool sections belong to the preview; reading them does not request a new experiment.

## Submit Learning Rate

When given an experiment report and asked for the next learning rate, call submit_learning_rate through snakelab_tool. Supply only learning_rate, a number greater than zero and at most one. All other configuration settings stay fixed.

Use the report's high scores and their progression to guide your choice. Each displayed epoch also includes its loss and the loss change since the previous displayed row. Negative change means loss decreased; N/A means unavailable. The final epoch is always included.

## Output

A successful submission returns the learning rate and new run ID. If the configuration has already completed on the same project version, the tool returns already_run and its report. Use those results to choose a different rate.

Submitting a learning rate requires a pending experiment decision. It cannot start arbitrary experiments during web chat.

- [Return to the Knowledge Base](/)
