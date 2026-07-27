#!/usr/bin/env bash
set -euo pipefail
git ls-files -z >/dev/null
echo "repository-hygiene verified"
