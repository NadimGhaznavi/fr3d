# Napkin Design

```
app/
    learning_rate/
        main-loop flow:
            Is an experiment running?
                Yes
                    wait
                No
                    continue

            Send 01 prompt
            Did LR get submitted?
                Yes
                    Has this LR value been used?
                        Yes
                            Send 02 prompt (max 3x, then restart main loop)
                            Has this LR value been used?
                                Yes
                                    Go back to Send 02 prompt
                                No
                                    Run experiment, restart main loop
                        No
                            Run experiment, restart main loop

                No
                    Restart loop
        
        tools/
            view an experiment report
            view an experiments summary report
            Submit an LR

        prompt_data/
            01 - Markdown for the LLM
            02 - Markdown for the LLM

        prompts/
            01 Outline the challenge
              - Make the *View experiment report* accessible
              - Make the *Submit an LR* tool accessible
            02 LR value already used
              - Make the *View experiments summary report* tool accessible
              - Make the *Submit an LR* tool accessible
```

# Clarifications

The code to retieve data from the DB and convert it to markdown (for the fr3d-report service) and JSON (for the LLM prompts) will live in a `reporting` directory parallel to the `app` folder.

*Already used* means that a query in the DB shows that that specific LR value was used in a simulation run.

Simulations don't fail. They never do: I build good ;)

To be clear: 
  - Prompts to the LLM are in MD. 
  - Reports with data for the LLM are in JSON.

Logging:
  - Keep the separate LLM/fr3d interactions in the llm-server.log, use a 3 char identifying "main loop id"
  - Keep the LLM reasoning in a llm-reasoning.log, Keep the current format that makes the reasoning human readable.

Each prompt will be a *fresh* conversation.

# Experiment Report

This report should contain:

- ID
- Runtime
- Learning rate
- High score
- Average score
- Median score
- Per episode data:
  - Score
  - Loss

# Experiments Summary Report

This report should contain

- Per experiement data:
  - ID
  - Learning rate
  - High score
