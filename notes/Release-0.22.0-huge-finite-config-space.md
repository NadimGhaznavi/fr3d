# Release 0.22.0 — Parameter Convergence

Extend the 0.21 round-robin search with an in-memory convergence rule.

## Behavior

- Track each parameter's successive completed LLM tweaks across round-robin
  cycles. Turns for other parameters do not interrupt its three-tweak window.
- Compare the best-ever `high_score` after the third completion against the best
  `high_score` immediately before the first of those three tweaks. If the gain
  is less than 2 points, mark the parameter `CONVERGED`. Exactly 2 points keeps
  it active. Use a rolling window of the most recent three tweaks.
- Improvements during intervening parameter turns also contribute to the best
  score gain. Gold promotion and backtracking preserve convergence and windows;
  backtracking never lowers the reference to an older baseline's score.
- Skip converged parameters in the existing fixed rotation. Once all currently
  eligible parameters converge, clear all convergence flags and windows, then
  continue from the current cursor. Exhausted finite dimensions do not prevent
  reopening. If no dimensions are eligible, retain existing backtracking and
  exhaustion handling.
- Epsilon and reward pairs each count as one parameter. Automatic sole-pair
  submissions are not LLM tweaks. Startup runs, waiting, duplicate proposals,
  rejected submissions, and failed experiments do not count. Existing failure
  handling remains in effect.
- Count a tweak only after its accepted run completes successfully, before
  choosing the next parameter. Repeated waiting polls cannot count a run twice.
- Restart clears convergence and windows and starts the rotation at the beginning.
  No database migration or persistent scheduling history is introduced.
- Log `parameter_converged` with `status=CONVERGED`, scores and gain;
  `parameter_skipped` for skipped converged turns; and
  `parameter_convergence_reset` when all eligible parameters reopen.

## Verification

All 68 affected search regression tests pass. The broader suite encountered
errors outside the changed search code; a knowledge-base test independently
fails because `/opt/fr3d/logs` is missing and cannot be created by the test user.

Tests cover the three-completion threshold, gains below/equal to/above two points,
rolling windows, interleaved turns, skipping, reopening with exhausted dimensions,
restart state, waiting, rejection, duplicates, failed runs, automatic pairs, and
score promotion during a window. Deployment and live-run verification remain
with the user.
