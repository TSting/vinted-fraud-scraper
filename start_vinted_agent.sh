#!/bin/bash

# Get the directory of this script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

echo "Opstarten van Vinted Fraud Scraper Agent..."
echo "Project map: $DIR"

# Ensure we are in the project root
cd "$DIR"

# Explicitly use the local venv's python and adk
LOCAL_PYTHON="$DIR/venv/bin/python3"
LOCAL_ADK="$DIR/venv/bin/adk"

if [ ! -f "$LOCAL_PYTHON" ]; then
    echo "Fout: Geen venv gevonden in $DIR/venv. Draai eerst de installatie stappen."
    exit 1
fi

# Set PYTHONPATH to include the current directory so adk can find the agent
export PYTHONPATH="$DIR:$PYTHONPATH"

echo "Gebruikt Python: $($LOCAL_PYTHON --version) van $LOCAL_PYTHON"

# Run adk web using the local environment
"$LOCAL_PYTHON" -m google.adk.cli.main web
