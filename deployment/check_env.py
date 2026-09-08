#!/usr/bin/env python3
"""Check a .env against what the bot actually reads.

Run this on the VPS before restarting the bot:

    python3 deployment/check_env.py

Exits non-zero if something is actually broken, so it can gate a deploy.
It only reads .env — it never writes or contacts Discord.
"""

import os
import sys

ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")

# Parsed by hand rather than via python-dotenv so this runs with a bare
# `python3` even outside the venv — a deploy check shouldn't need a working
# environment to tell you the environment is broken.
ENV = {}


def load(path):
    with open(path, "r", encoding="utf-8-sig") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            ENV[key.strip()] = val.strip().strip('"').strip("'")

# Renamed in 5e505e0. A .env still using the left-hand names silently disables
# the corresponding upload alerts.
RENAMED = {
    "YT_CHANNEL_1": "YT_ABITBEAST",
    "YT_CHANNEL_2": "YT_LETSBEAST",
    "YT_CHANNEL_3": "YT_REDSHIF8",
}

YT_VARS = ["YT_ABITBEAST", "YT_LETSBEAST", "YT_BYTEBEAST", "YT_REDSHIF8"]

# Everything added recently. All optional — listed so you can see what default
# you're getting rather than having to guess.
OPTIONAL = [
    ("UPLOAD_ROLE", "1546795007040552990 (Upload Squad)"),
    ("STREAM_ROLE", "1546795078931062825 (Stream Squad)"),
    ("YT_SHORTS_CHANNEL", "0 -> Shorts posted alongside uploads"),
    ("YT_PING_ON_SHORTS", "false -> Shorts never ping"),
    ("YT_AUTO_THREAD", "true -> thread opened per upload"),
    ("YT_AUTO_THREAD_SHORTS", "false"),
    ("ALERT_CHANNEL", "falls back to LOGGING_CHANNEL"),
    ("MOD_PING_ROLE", "0 -> raid alerts stay quiet"),
    ("RAID_JOIN_COUNT", "10"),
    ("RAID_JOIN_WINDOW", "30"),
    ("RAID_WATCH_MINUTES", "10"),
    ("RAID_COORD_USERS", "4"),
    ("RAID_COORD_WINDOW", "20"),
]

errors = []
warnings = []


def value(name):
    return ENV.get(name, "").strip()


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else ENV_PATH
    if not os.path.exists(path):
        print("No .env found at %s" % os.path.abspath(path))
        return 2
    load(path)

    print("Checking %s\n" % os.path.abspath(path))

    # --- required -----------------------------------------------------
    if not value("DISCORD_TOKEN"):
        errors.append("DISCORD_TOKEN is not set — the bot cannot start.")
    else:
        print("  OK    DISCORD_TOKEN is set")

    # --- the rename trap ----------------------------------------------
    stale = [old for old in RENAMED if value(old)]
    if stale:
        errors.append(
            "Your .env still uses the OLD YouTube variable names: %s\n"
            "        These are ignored now. Rename them:\n%s"
            % (
                ", ".join(stale),
                "\n".join("          %s  ->  %s" % (o, RENAMED[o]) for o in stale),
            )
        )

    configured = [v for v in YT_VARS if value(v) and value(v) != "0"]
    if not configured:
        errors.append(
            "No YouTube channels are configured, so upload alerts are DISABLED.\n"
            "        Set at least one of: %s" % ", ".join(YT_VARS)
        )
    else:
        print("  OK    %d/%d YouTube channel(s) configured: %s"
              % (len(configured), len(YT_VARS), ", ".join(configured)))
        missing = [v for v in YT_VARS if v not in configured]
        if missing:
            warnings.append("These YouTube channels are unset and will be skipped: %s"
                            % ", ".join(missing))

    if not value("KICK_CHANNEL_1") or value("KICK_CHANNEL_1") == "0":
        warnings.append("KICK_CHANNEL_1 unset — Kick live alerts have nowhere to post.")
    else:
        print("  OK    KICK_CHANNEL_1 is set")

    # --- the alert-channel trap ---------------------------------------
    if value("ALERT_CHANNEL") == "0":
        warnings.append(
            "ALERT_CHANNEL=0 is treated as unset (falls back to LOGGING_CHANNEL). "
            "Remove the line or give it a real channel id."
        )

    # --- optional, informational --------------------------------------
    print("\nOptional settings (defaults are fine — shown so you know what you get):")
    for name, default in OPTIONAL:
        got = value(name)
        if got and got != "0":
            print("  set   %-22s = %s" % (name, got))
        else:
            print("  ----  %-22s   using default: %s" % (name, default))

    # --- verdict -------------------------------------------------------
    print()
    for w in warnings:
        print("  WARN  %s" % w)
    for e in errors:
        print("  ERROR %s" % e)

    print()
    if errors:
        print("NOT OK — %d problem(s) above must be fixed." % len(errors))
        return 1
    if warnings:
        print("OK with %d warning(s) — the bot will run." % len(warnings))
        return 0
    print("All good. Your existing .env is enough.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
