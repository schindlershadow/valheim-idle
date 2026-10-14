#!/usr/bin/env python3
# Holds the Valheim UDP ports while the server is stopped; first real join packet starts it.
import json, os, select, socket, subprocess, sys, time, urllib.request

PORTS = (2456, 2457, 2458)
WOL_PORT = 2459  # HA button sends a WoL magic packet here
WOL_MAC = bytes.fromhex("02564c480001")
MAGIC = b"\xff" * 6 + WOL_MAC * 16
socks = []
for p in PORTS:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", p))
    socks.append(s)
wol = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
wol.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
wol.bind(("0.0.0.0", WOL_PORT))
socks.append(wol)
print(f"waiting for join packets on UDP {PORTS}", flush=True)

def discord(msg):
    try:
        url = open(os.path.expanduser("~/.config/valheim-discord/webhook_url")).read().strip()
        req = urllib.request.Request(url, json.dumps({"content": msg}).encode(),
                                     {"Content-Type": "application/json", "User-Agent": "valheim-wake/1.0"})
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"discord post failed: {e}", flush=True)

while True:
    ready, _, _ = select.select(socks, [], [])
    for s in ready:
        data, addr = s.recvfrom(2048)
        if s is wol:
            if data[:len(MAGIC)] != MAGIC:
                continue
        elif data[:4] == b"\xff\xff\xff\xff":  # Steam A2S server-browser query, not a join
            continue
        print(f"{time.ctime()}: packet from {addr[0]}:{addr[1]} on {s.getsockname()[1]} ({len(data)} B) -> starting valheim", flush=True)
        discord(":bell: Connection attempt detected, waking the server up...")
        subprocess.run(["systemctl", "--user", "start", "--no-block", "valheim.service"])
        time.sleep(300)
        sys.exit(0)
