#!/usr/bin/env bash
set -eu
cp -R "$(dirname "$0")/files/." .
mkdir -p src tests; [ -f src/handler.py ] || echo x > src/handler.py
git init -q 2>/dev/null || true
git remote add origin https://github.com/acme/widgets.git 2>/dev/null || true
