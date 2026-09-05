# Standalone learning-rate prompt

From the source checkout, with `requirements.txt` installed:

```sh
python -m dialogue.poke_fr3d
python -m dialogue.poke_fr3d > /tmp/learning-rate.md
```

The command reads `/etc/fr3d/database.env` when present. Use `--env-file PATH`
for another credentials file. Existing `FR3D_DB_*` environment variables take
precedence. The database is always `DDatabase.SNAKE_LAB_DB_NAME` (`snakelab`),
regardless of `FR3D_DB_NAME`. The account needs SELECT access to that database.
For local socket authentication, `--unix-socket /run/mysqld/mysqld.sock` is available.

All completed runs are included by default. To select a comparison:

```sh
python -m dialogue.poke_fr3d --run-id 1 --run-id 2 --run-id 3
```

Run IDs are numeric `simulation_runs.id` values, not UUIDs. Runs must have the
same project version and configuration except for `training.learning_rate`,
and contain every configured epoch. Scores and losses are calculated from
`simulation_episodes`, not cached run summaries. NULL losses are excluded from
mean loss; final loss is taken from the final epoch, even if NULL. High-score
tables show record-setting epochs plus the first and final epochs.

The introduction and task/tool instructions come from `templates/learning-rate.md`;
`--template PATH` selects another template with the same section headings.
Only the populated Markdown goes to stdout. Errors go to stderr with a nonzero
exit status. No database writes, LLM requests, tool calls, or submissions occur;
`submit_learning_rate` remains only a proposed interface in the generated prompt.
This module is not yet included in service startup or installation.
