Your instinct is spot on, Nadim. This is a classic application of the Facade Pattern.
The Orchestrator should act as a "translator" that absorbs all of snake-lab's complexity (JSON schemas, database joins, ZMQ protocols) and presents Fr3d with a clean, simplified, high-level interface. Fr3d's only job is to look at a simplified comparison and reason about the next step.
Here is what that simplified data contract looks like at the design level.
The Simplified Data Contract
1. What the Orchestrator Presents to Fr3d (The Input)
Instead of raw configs or database rows, the Orchestrator queries MariaDB, calculates the deltas, and feeds Fr3d a tight, standardized text block. Fr3d only sees this:

=== EXPERIMENT COMPARISON ===

[Action Taken in Previous Run]
- Parameter Tweaked: training.learning_rate
- Change: 0.001 → 0.002

[Previous Run Results]
- High Score: 150
- Avg Score (Last 10): 120
- Avg Loss (Last 10): 0.45

[Current Run Results]
- High Score: 180
- Avg Score (Last 10): 145
- Avg Loss (Last 10): 0.38

[Calculated Deltas]
- High Score: +30 (+20.0%)
- Avg Score: +25 (+20.8%)
- Avg Loss: -0.07 (Improved convergence)
=============================

123456789101112131415161718192021
2. What Fr3d Returns (The Output)
Because the input is so structured, Fr3d's output can be a highly constrained JSON object. It doesn't need to output the whole config, just its decision:

{
  "analysis": "The increased learning rate improved both score and loss convergence without causing instability.",
  "next_parameter": "training.learning_rate",
  "next_value": 0.003,
  "hypothesis": "We can push the learning rate slightly higher to see if convergence speed improves further before hitting instability."
}

123456
3. What the Orchestrator Does Next (The Heavy Lifting)
Parses Fr3d's JSON.
Validates that next_parameter is in the allowed list and next_value is within bounds.
Fetches the actual full JSON config of the current run from MariaDB.
Applies the single tweak programmatically.
Submits the new, complete config to snake-lab via ZMQ.
Waits: Polls the database every 30 seconds for the status to change from running to completed (or failed).
Once completed, it loops back to Step 1, generating a new comparison between the run that just finished and the one before it.
Why This is the Sweet Spot for a 4B Model
Zero Cognitive Overload: Fr3d doesn't have to parse nested JSON, understand database schemas, or worry about ZMQ. It just reads a "report card" and decides what to try next.
Guarded Action Space: Fr3d can only suggest a parameter and a value. The Orchestrator holds the keys to the actual configuration, preventing Fr3d from accidentally deleting a required field or hallucinating a new parameter.
Built-in Memory: By always comparing N to N − 1, Fr3d inherently understands the gradient of its own experiments without needing a massive context window of past runs.
Design Questions for You:
The Metrics: Does the [Calculated Deltas] section above (High Score, Avg Score, Avg Loss) give Fr3d enough information to make a good decision? Or should we add something like "Avg Epsilon" or "Time to Converge"?
The Failure State: If a run fails (e.g., status = 'failed'), how should the Orchestrator present that to Fr3d? (e.g., [Current Run Results]: FAILED - Error: NaN loss detected).
The Waiting Mechanism: Does a simple 30-second database poll by the Orchestrator sound acceptable for this first iteration, or is the latency of long-running simulations going to be a problem?
We can refine this contract until it feels exactly right before we write a single line of implementation code.