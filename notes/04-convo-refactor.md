# General Info

Release **v0.14.4**

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
            Is the LR valid and new?
                Yes
                    Send to Snake Lab
                No
                    Restart main-loop
        No
            Restart main-loop
```

