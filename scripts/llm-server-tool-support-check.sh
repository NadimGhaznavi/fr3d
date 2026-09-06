#!/bin/bash

curl http://localhost:51970/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "test-model",
    "messages": [
      {
        "role": "user",
        "content": "What is the weather like in Paris today?"
      }
    ],
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "get_current_weather",
          "description": "Get the current weather in a given location",
          "parameters": {
            "type": "object",
            "properties": {
              "location": {
                "type": "string",
                "description": "The city and state, e.g. San Francisco, CA"
              },
              "unit": {
                "type": "string",
                "enum": ["celsius", "fahrenheit"]
              }
            },
            "required": ["location"]
          }
        }
      }
    ],
    "tool_choice": "auto"
  }'