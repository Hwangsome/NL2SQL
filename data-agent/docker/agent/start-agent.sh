#!/bin/sh
set -eu

.venv/bin/python docker/agent/wait_for_dependencies.py
exec .venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
