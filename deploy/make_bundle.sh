#!/usr/bin/env bash
# Code-only by default. --with-state holds both bot locks throughout archive creation.
# Activate your Python environment, or set PYTHON to the Python executable to use.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
exec "${PYTHON:-python}" deploy/make_bundle.py "$@"
