# Latest Prompts Dashboard Layout

## Goal

Change the **Latest prompts** page from a vertical list of parameters into a matrix.

This page is a troubleshooting/sanity-check dashboard only.

It is **not an audit log** and does not need to show prompt history. 

For each parameter, retain and expose only the **most recently saved prompt of each prompt type**.

---

## Required Layout

Render the prompts as a table/matrix.

Each **row** represents one parameter or parameter group.

Each **prompt column** represents one prompt type:

1. Initial
2. Comparison
3. No reruns
4. Invalid value

There should also be a left-most row label containing the parameter name.

Conceptually:

| Parameter | Initial | Comparison | No reruns | Invalid value |
| --- | --- | --- | --- | --- |
| epsilon_pair | View | View | View | View |
| model.hidden_size | View | View | View | View |
| reward_pair | View | View | View | View |
| training.batch_size | View | View | View | View |
| training.gamma | View | View | View | View |
| training.learning_rate | View | View | View | View |
| training.sequence_length | View | View | View | View |

The four columns after `Parameter` are the four prompt-type columns.

---

## Missing Prompt Types

Not every parameter will necessarily have encountered every prompt type yet.

If no saved prompt exists for a particular parameter/type combination, render the cell as something visually quiet such as:

```text
—
```

Do not:

- invent a link
- fall back to another prompt type
- hide the entire row
- hide the entire column

Example:

| Parameter | Initial | Comparison | No reruns | Invalid value |
| --- | --- | --- | --- | --- |
| epsilon_pair | View | View | — | View |
| model.hidden_size | View | View | View | — |

---

## Visual Intent

The page should read horizontally:

```text
                     PROMPT TYPE

                   Initial   Comparison   No reruns   Invalid value
epsilon_pair         link       link          —            link
model.hidden_size    link       link         link           —
reward_pair          link        —           link          link
training.gamma       link       link         link          link
```

The primary question this page should answer is:

> "For this parameter, what did each kind of LLM prompt most recently look like?"

It should be possible to scan across one row and quickly inspect all four prompt states for that parameter.

---