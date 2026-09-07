# General Info

- This is scheduled for release **v0.15.2**
- The main loop is one conversation thread
- This requires a new `summary report` for epsilon tool

```
main-loop:
    Is an experiement running in the Snake Lab?
        Yes
            Sleep, restart main loop
        No
            Proceed
    
    Send SUMMARY to LLM. Wait for VALUE.

    Did a VALUE arrive?
        Yes
            Is the VALUE valid?
                No
                    Send INVALID_VALUE to LLM.
                    Return to 'Did a VALUE Arrive?'
                Yes
                    Proceed

            Is the VALUE unique?
                No
                    Send NO_RERUNS to LLM.
                    Return to 'Did a VALUE arrive?'.
                Yes
                    Proceed

            Send to Snake Lab
            Restart main-loop
                    
        No
            Restart main-loop
```

SUMMARY : summary_report.md
NO_RERUNS : no_reruns.md
INVALID_VALUE : invalid_value.md


