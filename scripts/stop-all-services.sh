#!/bin/bash
set -e

systemctl stop fr3d-watchdog
systemctl stop fr3d-server
systemctl stop fr3d-report
systemctl stop llm-server
