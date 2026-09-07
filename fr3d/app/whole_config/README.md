# Whole-configuration search

`fr3d-server.service` runs `fr3d.app.whole_config.main_loop`. The server keeps
its journal and report interfaces; the experiment task performs serial searches
over the complete Snake Lab configuration. The previous epsilon and learning-rate
modules remain available for historical reference and their existing tests.

- `configuration.py` reads schema defaults, exposes searchable fields, and
  validates complete candidates while enforcing the five fixed settings.
- `reports.py` queries Snake Lab's `configurations` columns for comparable
  history and duplicates, and episode scores for gold ranking.
- `selection.py` chooses among the least explored parameters, excluding
  exhausted integer ranges relative to current gold.
- `conversation.py` sends one parameter's task and report to the LLM. It uses
  the shared conversation context budget and report snapshots. Invalid values
  and duplicates receive corrective prompts within the same conversation.
- `archive.py` appends the initial gold and subsequent promotions to
  `/opt/fr3d/logs/gold.jsonl`, including the previous gold run ID.
- `main_loop.py` submits the baseline, observes completion, promotes strictly
  better scores, and submits candidates changing one parameter from gold.

The runtime requires Snake Lab's v1, v2, and v3 database schemas and the complete
configuration schema. Installation and upgrade copy `pages/snake-lab-schemas`
alongside the Python packages; the schema is read from that installed location.
Fr3d reads Snake Lab's database and submits configurations through its existing
ZMQ control client. It does not apply Snake Lab database migrations.

Unexpected errors crash the experiment task and service. The service unit uses
`Restart=no`; there is no recovery or submission retry. A search with no eligible
parameters waits until the operator stops the service.

Run the focused tests with:

```sh
venv/bin/python -m unittest discover -s tests -p test_whole_config.py -v
```
