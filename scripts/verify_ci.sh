#!/usr/bin/env bash
set -euo pipefail

# Backend CI must be reproducible without sibling repositories or live services.
uv run pytest -m "not integration" -q
