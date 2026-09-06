# Snake Lab Tool

The Snake Lab Tool lets Fr3d choose the learning rate for the next [Snake Lab](/snake-lab) experiment.

## Input

When given an experiment report and asked for the next learning rate, call submit_learning_rate through snakelab_tool. Supply only learning_rate, a number greater than zero and at most one. All other configuration settings stay fixed.

Use the report's high scores and their progression to guide your choice. Each displayed epoch also includes its loss and the loss change since the previous displayed row. Negative change means loss decreased; N/A means unavailable. The final epoch is always included.

## Output

A successful submission returns the learning rate and new run ID. If the configuration has already completed on the same project version, the tool returns already_run and its report. Use those results to choose a different rate.

The tool requires a pending experiment decision. It cannot start arbitrary experiments during web chat.

- [Return to the Knowledge Base](/)
