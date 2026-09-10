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
submission request. `DFr3d.PROMPT_TIMEOUT` sets a 240-second deadline for the
whole conversation, including report lookups. HTTP timeouts count as no submission
too. The five-second `FR3D_POLL_INTERVAL` applies only after an iteration ends; it
does not send new prompts while an HTTP request is pending. Early replies without
a completed tool call log their finish reason and tool-call count before the loop
follows its normal retry path. Cancellation stops the conversation
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

- `/`: most recent saved parameter summary supplied to the LLM, displayed as
  indented JSON. Refresh loads the newest available summary.
- `/reports/<snapshot-id>/`: the saved report for a particular conversation.
- `/prompts/`: parameters with saved LLM requests. Open a parameter to select
  its initial, summary, or correction prompt. Each type retains its latest sample,
  including the full request after context trimming.
- `/prompts/<parameter>/<prompt-type>/`: the latest sample of that prompt type.
- Add `?format=json` to any of these URLs for a JSON response.

Prompt types appear as requests occur; previously overwritten samples cannot be
recovered. Existing unclassified samples remain available on the parameter page.

The page preserves the report's fields and values, including `null`; it does not
convert JSON to Markdown, regenerate a report, or query the database. Before a
parameter summary has been saved, the homepage displays a waiting message.
Older learning-rate snapshots do not replace the latest parameter summary.

Snapshot files remain in `/opt/fr3d/logs/reports/` and survive upgrades. Removed
experiment, legacy, best/worst, and journal web routes return 404; their stored
data is preserved.

## Archived implementation

The previous app lives in `../app_legacy/`. Its imports and regression tests now
refer to that package. `python -m fr3d.server.Fr3dServer` still launches the archived
loop for reference. Run only one FR3D service at a time.

The source systemd unit selects the new app. Apply it with the existing upgrade
workflow when ready to deploy; editing this checkout does not restart services.

## Watchdog

`fr3d-watchdog.service` checks both services every 60 seconds. It restarts
`fr3d-server.service` when systemd reports `inactive` or `failed`, and retains
the LLM HTTP `/health` check and restart behavior. Fr3d is checked only for
whether its service is running; there is no application health probe.
Logs are written to `/opt/fr3d/logs/fr3d-watchdog.log` and the systemd journal.

For maintenance, stop `fr3d-watchdog` before stopping either server, or use
`scripts/stop-all-services.sh`. Start the watchdog after the servers.
The upgrade script removes the old `llm-watchdog` unit and enables the replacement.
