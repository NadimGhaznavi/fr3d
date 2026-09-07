#!/bin/bash

echo -n "Starting llm-server: "
systemctl start llm-server
echo "[DONE]"

# It takes the HP z400 with the M4000 GPU about 5 seconds to start
# the LLM. 

sleep 7

echo -n "Starting llm-watchdog: "
systemctl start llm-watchdog
echo "[DONE]"

echo -n "Starting fr3d-report: "
systemctl start fr3d-report
echo "[DONE]"

echo -n "Starting fr3d-server: "
systemctl start fr3d-server
echo "[DONE]"



