#!/bin/bash

echo -n "Stopping fr3d-server: "
systemctl stop fr3d-server
echo "[DONE]"

echo -n "Stopping fr3d-report: "
systemctl stop fr3d-report
echo "[DONE]"

echo -n "Stopping llm-watchdog: "
systemctl stop llm-watchdog
echo "[DONE]"

echo -n "Stopping llm-server: "
systemctl stop llm-server
echo "[DONE]"
