# Overview

The challenge that this release aims to fix is the situation where a high score may be the result of a lucky seed.


# New seed value

The seed should just be incremented by 1.

# The Gold Config

Let's assume we have a gold config with a score of 50

- The gold config is submitted to the Snake Tower with the new seed
- The high score of this run is 39
- The system now sets the high score to beat as 39
- The existing gold config continues to be the gold config

# New Flow

```
seed 1970
    ↓
establish / continue gold
    ↓
round-robin cycle
    ↓
new gold? ── yes → reset stagnation counter
    │
    no
    ↓
round-robin cycle #2
    ↓
round-robin cycle #3
    ↓
still no improvement
    ↓
rotate seed → 1971
    ↓
rerun CURRENT GOLD unchanged
    ↓
that result becomes the new seed's gold score
    ↓
resume round-robin
```

# Implementation details

- A cycle is one pass through the parameter order, skipping exhausted/converged
  dimensions. Count it after its final submitted experiment completes. Automatic
  pair experiments count as turns too.
- A new gold immediately clears stagnation; its cycle does not count as stagnant.
- After the new seed baseline completes, clear convergence, backtracking dead
  ends, and the round-robin cursor. Resume at the first dimension.
- Gold selection, comparisons, and backtracking stay within the active seed.
- Recover the active seed from the highest seed in stored configurations. Existing
  run-state checks wait for its baseline and stop on failed/unfinished idle runs.
  Cycle counters reset to zero after restart.
- Log rotation (old/new seed and run IDs) and baseline completion (new score to
  beat) in `fr3d.log`. Log the recovered seed and score on restart.
- The Snake Lab v2 schema must allow incremented seeds. The matching schema change
  replaces the seed enum with a nonnegative integer constraint; deploy it with
  this release.
