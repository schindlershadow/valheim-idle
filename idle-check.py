#!/usr/bin/env python3
# Stops valheim.service after IDLE_MIN minutes with no players.
import re, subprocess, time
from datetime import datetime

import os
LOG = os.path.join(os.environ.get("VALHEIM_SERVER_DIR", os.path.expanduser("~/valheim-server")), "BepInEx", "LogOutput.log")
IDLE_MIN = float(os.environ.get("IDLE_MIN", 20))
GRACE_MIN = float(os.environ.get("GRACE_MIN", 15))

def sh(*a):
    return subprocess.run(a, capture_output=True, text=True).stdout.strip()

if sh("systemctl", "--user", "is-active", "valheim.service") != "active":
    raise SystemExit
since = int(sh("systemctl", "--user", "show", "valheim.service", "-p", "ActiveEnterTimestampMonotonic", "--value") or 0) / 1e6
with open("/proc/uptime") as f:
    up = float(f.read().split()[0])
if up - since < GRACE_MIN * 60:
    raise SystemExit

ts_re = re.compile(r"(\d\d/\d\d/\d{4} \d\d:\d\d:\d\d):")
last_conn = None
last_event = 0.0
with open(LOG, errors="replace") as f:
    for line in f:
        m = ts_re.search(line)
        if not m:
            continue
        t = datetime.strptime(m.group(1), "%m/%d/%Y %H:%M:%S").timestamp()
        c = re.search(r"Connections (\d+) ZDOS", line)
        if c:
            last_conn = int(c.group(1))
        elif re.search(r"Got handshake|Got connection|Got character ZDOID|Closing socket|has wrong password|Peer .* disconnected", line):
            last_event = t

if last_conn:
    raise SystemExit
if time.time() - last_event < IDLE_MIN * 60:
    raise SystemExit
print(f"{time.ctime()}: no players for {IDLE_MIN}+ min, stopping valheim", flush=True)
subprocess.run(["systemctl", "--user", "stop", "valheim.service"])
