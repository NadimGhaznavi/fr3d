# General Info

Release **v0.14.5**

The main loop is one conversation thread.

```
main-loop:
    Is an experiement running in the Snake Lab?
        Yes
            Sleep, restart main loop
        No
            Proceed
    
    Send SUMMARY to LLM. Wait for LR.

    Did an LR arrive?
        Yes
            Is the LR valid?
                No
                    Send INVALID_LR to LLM.
                    Return to 'Did an LR Arrive?'
                Yes
                    Proceed

            Is the LR unique?
                No
                    Send NO_RERUNS to LLM.
                    Return to 'Did an LR arrive?'.
                Yes
                    Proceed

            Send to Snake Lab
            Restart main-loop
                    
        No
            Restart main-loop
```

SUMMARY : summary_report.md
NO_RERUNS : no_reruns.md
INVALID_LR : invalid_lr.md
