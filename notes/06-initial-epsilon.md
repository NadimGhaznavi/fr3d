# General Info

Release **v0.14.9**

The main loop is one conversation thread.

```
main-loop:
    Is an experiement running in the Snake Lab?
        Yes
            Sleep, restart main loop
        No
            Proceed
    
    Send FIRST_CONTACT to LLM. Wait for the VALUE; epsilon_decay.

    Did a VALUE arrive?
        Yes
            Is the VALUE valid?
                No
                    Send INVALID_VALUE to LLM.
                    Return to 'Did a VALUE Arrive?'
                Yes
                    Proceed

            Send to Snake Lab
            Restart main-loop
                    
        No
            Restart main-loop
```

**NOTE** 
An operator will monitor the environment. When the LLM has started a 2nd experiment the LLM will be shutdown. The main loop will be manually terminated.