#!/bin/bash
set -e

systemctl start llm-server
sleep 7
systemctl start fr3d-report
systemctl start fr3d-server
systemctl start fr3d-watchdog
