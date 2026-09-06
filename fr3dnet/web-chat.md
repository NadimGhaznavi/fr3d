# Web Chat

The `llama-server` provices a built-in web-based chat interface to the underlying LLM.

The interface exposes model activity such as reasoning and tool calls in expandable sections, making it useful both for normal conversation and for observing how Fr3d works through a request.

The web chat also provides insight into the MCP tools configured for `llama-server`. When Fr3d decides that a tool is needed, the web interface shows the tool invocation, its input, and the returned result before generation continues.

The web interface is useful not only as a chat client, but also as a lightweight development and diagnostic console for testing Fr3d's knowledge base, journal, weather, and other tool integrations.