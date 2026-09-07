A. Context Bloat (4,137 Token Prompt)
Your prompt is already using 4,137 tokens just to get to this point.
You have a 12,288 context limit.
You are already at ~33% capacity on this turn.
If the tool returns a large report, the model generates another 800 tokens of reasoning, and you loop again, you will hit your 12k limit in just 2 or 3 more turns.
Fix: Ensure your backend is actively managing the chat history. Once the context approaches ~8,000 tokens, you should start summarizing or dropping the oldest tool results/reasoning blocks to prevent the prompt from exceeding 12k (which would cause truncated = 1 and break the agent's memory).