#!/usr/bin/env bash

set -u

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_dir"

python_bin=".venv/bin/python"
batch_size=100
batch_number=1

if [ ! -x "$python_bin" ]; then
  echo "error: $python_bin not found; create the virtualenv and install the project first" >&2
  exit 1
fi

while true; do
  echo "batch $batch_number: syncing up to $batch_size pending companies"
  "$python_bin" -m finance_research_lab.cli sync-company-profiles --limit "$batch_size"
  batch_status=$?
  if [ "$batch_status" -ne 0 ]; then
    echo "stopped: batch $batch_number failed; inspect data/company_profile_cache/last-run.json" >&2
    exit "$batch_status"
  fi

  pending_count=$(
    "$python_bin" -c \
      "import json; print(json.load(open('data/company_profile_cache/last-run.json'))['result']['pending'])"
  )
  if [ "$pending_count" -eq 0 ]; then
    echo "completed: all company profiles are cached"
    exit 0
  fi

  echo "batch $batch_number completed: pending=$pending_count"
  batch_number=$((batch_number + 1))
done
