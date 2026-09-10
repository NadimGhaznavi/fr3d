# Objective

The idea behind this change is to give the LLM access to the simulation data from previous runs with the same golden where only the seed has changed/rotated.

Historical simulation data must be included for all parameter types, including continuous parameters and parameter pairs, to help guide the LLM.

For each parameter value or pair, historical runs must match that value or pair and every other golden configuration setting except the seed. History contains completed runs from other seeds with an available high score. Keep zero scores and repeated scores, and sort each `history` array numerically from lowest to highest. Use `[]` when no qualifying history exists.

`results` describes runs matching the current seed. Historical scores provide evidence for selection but do not mark a value as tested on the current seed or change its eligibility. The prompts must explain this distinction.

For finite parameters, show the valid grid values or pairs. For continuous parameters, show the observed values or pairs from both current-seed runs and qualifying historical runs; do not invent a finite grid. A value observed only on another seed has `results: "UNTESTED"` and its historical scores. The LLM can also propose continuous values that have never been observed. Sort scalar entries numerically by value and pair entries numerically by their component values in the existing parameter order.

```
"value_results": [
  {
    "value": 8,
    "results": "UNTESTED",
    "history": [35, 38]
  },
  {
    "value": 16,
    "results": "UNTESTED",
    "history": [37, 39, 41]
  },
      .
      .
      .
```
