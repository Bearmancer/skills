#!/usr/bin/env bash
set -eu
cp -R "$(dirname "$0")/files/." .
mkdir -p src tests; [ -f src/handler.py ] || echo x > src/handler.py
