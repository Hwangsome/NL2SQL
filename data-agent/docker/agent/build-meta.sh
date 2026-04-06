#!/bin/sh
set -eu

.venv/bin/python docker/agent/wait_for_dependencies.py
exec .venv/bin/python -m app.scripts.build_meta_knowledge --config conf/meta_config.yaml
