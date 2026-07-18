#!/bin/bash
set -euo pipefail

# Navigate to the bot directory
cd /home/youruser/bitbot

# Activate Virtual Environment
source venv/bin/activate

# Run the Bot. -u keeps stdout unbuffered so `journalctl -u bitbot -f` shows log
# lines as they happen instead of in delayed chunks. exec means systemd tracks
# the Python process directly, so Restart= and stop signals work properly.
exec python3 -u main.py
