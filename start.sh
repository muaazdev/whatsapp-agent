#!/bin/sh
cd "$(dirname "$0")"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env - open it, paste your keys, then run ./start.sh again."
  exit 0
fi
python3 -m pip install -q -r requirements.txt
python3 agent.py
