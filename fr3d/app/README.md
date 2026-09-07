# Learning-rate app

The FR3D service starts at `fr3d.app.learning_rate.main_loop`:

```sh
python -m fr3d.app.learning_rate.main_loop
```

`learning_rate/main_loop.py` owns the experiment sequence. It waits for Snake Lab,
asks prompt 01 for an LR, and checks all recorded runs for that value. A duplicate
leads to prompt 02, up to three times. An absent or invalid replacement retains
the current value. A fresh value starts one experiment; the loop then waits again.
An absent submission from prompt 01 restarts the loop after the polling interval.

Every prompt starts a fresh conversation. Tool requests and responses stay within
that conversation. Each conversation allows three report lookups followed by a
submission request and has a 240-second timeout. Cancellation stops the conversation
and service transport. A prompt timeout counts as no submission.

- `learning_rate/prompt_data/`: editable Markdown instructions.
- `learning_rate/prompts/`: prompt construction and tool availability.
- `learning_rate/tools/`: report access and LR submission validation.
- `learning_rate/conversation.py`: LLM HTTP requests and tool execution.
- `../reporting/`: database queries, JSON/Markdown rendering, and report snapshots.

Submission tools propose a number; only the main loop starts experiments. The
configuration comes from the latest completed experiment, with only its LR changed.
At least one completed experiment is therefore required. Unlike the archived app,
this flow does not replay three baseline experiments on a Snake Lab version change.
“Used” includes all recorded runs, irrespective of status, version, or other settings.

Interactions and report snapshot URLs go to `llm-server.log`. A three-character
main-loop ID joins the prompt conversations; IDs can recur, so use timestamps too.
The current task, readable model reasoning, and the model’s response appear in
`llm-reasoning.log`, including tool names and arguments. Input prompt text, report
data, and response metadata stay in the interaction log. When no separate reasoning is returned, a short notice appears instead.

The existing ZMQ server provides journal and archived report endpoints. Its old
external LR submission endpoint rejects requests while the new loop is active;
submissions belong to that loop's prompt conversation. No second decision loop runs.

## Report server

- `/`: latest completed experiment.
- `/experiments/`: completed experiments summary.
- `/experiments/123/`: experiment 123.
- `/reports/<snapshot-id>/`: exact report data supplied to an LLM conversation.
- Add `?format=json` to these URLs to read the underlying JSON.
- `/legacy/`, `/best-worst/`, and `/journal/`: retained existing views.

Markdown displays the same values without rounding. `null` displays as
“Not available”; all episode rows remain present. Runtime is elapsed seconds from
start to completion, including pauses and excluding queue time.

Snapshot JSON files live under `/opt/fr3d/logs/reports/` and survive normal upgrades.
They are created only when a prompt requests a report. Current database views can
change over time; snapshot views do not. There is no automatic snapshot retention
policy yet.

## Archived implementation

The previous app lives in `../app_legacy/`. Its imports and regression tests now
refer to that package. `python -m fr3d.server.Fr3dServer` still launches the archived
loop for reference. Run only one FR3D service at a time.

The source systemd unit selects the new app. Apply it with the existing upgrade
workflow when ready to deploy; editing this checkout does not restart services.
