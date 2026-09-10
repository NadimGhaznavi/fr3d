#!/bin/bash
set -e

systemctl stop fr3d-watchdog
systemctl stop fr3d-server
systemctl stop fr3d-report
systemctl stop llm-server

sleep 1

systemctl start llm-server
sleep 7
systemctl start fr3d-report
systemctl start fr3d-server
systemctl start fr3d-watchdog
