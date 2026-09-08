#!/bin/bash
set -euo pipefail

# Navigate to the bot directory
cd /home/youruser/bitbot

# Activate Virtual Environment.
# `set -u` is relaxed across the source: activate scripts read unset variables
# such as PS1 and PYTHONHOME, and older ones aren't written to survive it. A
# failure here would leave systemd restarting a bot that never starts.
set +u
# shellcheck disable=SC1091
source venv/bin/activate
set -u

# Run the Bot. -u keeps stdout unbuffered so `journalctl -u bitbot -f` shows log
# lines as they happen instead of in delayed chunks. exec means systemd tracks
# the Python process directly, so Restart= and stop signals work properly.
exec python3 -u main.py
