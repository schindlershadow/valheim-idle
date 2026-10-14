#!/usr/bin/env python3
"""Per-world profiles for the Valheim server.

CLI (used by start.sh):
  worldctl.py world       print the active world name
  worldctl.py modifiers   print "-modifier x y ..." launch flags for the active world
  worldctl.py apply       write the active world's profile into the BepInEx configs
"""
import json
import os
import re
import sys
import fcntl
from contextlib import contextmanager

HOME = os.path.expanduser("~")
BASE = os.path.join(HOME, "valheim-idle")
PROFILES = os.path.join(BASE, "profiles")
STATE = os.path.join(BASE, "state.json")
SERVER_DIR = os.environ.get("VALHEIM_SERVER_DIR", os.path.join(HOME, "valheim-server"))
CONFIG_DIR = os.path.join(SERVER_DIR, "BepInEx", "config")
CC_CFG = os.path.join(CONFIG_DIR, "ArgusMagnus.ServersideQoL.ControlCenter.cfg")
CLU_CFG = os.path.join(CONFIG_DIR, "ArgusMagnus.ServersideQoL.CreatureLevelUp.cfg")
WORLDS_DIR = os.path.join(HOME, ".config/unity3d/IronGate/Valheim/worlds_local")
LOG = os.path.join(SERVER_DIR, "BepInEx", "LogOutput.log")

DEFAULT_WORLD = os.environ.get("VALHEIM_DEFAULT_WORLD", "MyWorld")
NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,30}$")

MODIFIERS = {
    "Combat": ["VeryEasy", "Easy", "Default", "Hard", "VeryHard"],
    "DeathPenalty": ["Casual", "VeryEasy", "Easy", "Default", "Hard", "Hardcore"],
    "Resources": ["MuchLess", "Less", "Default", "More", "MuchMore", "Most"],
    "Raids": ["None", "MuchLess", "Less", "Default", "More", "MuchMore"],
    "Portals": ["Casual", "Default", "Hard", "VeryHard"],
}

# Setting that lives in another mod's config: name -> (file, section)
EXTRA = {"MaxLevelIncrease": (CLU_CFG, "CreatureLevelUp")}

TEMPLATE = {
    "modifiers": {"Combat": "Hard", "DeathPenalty": "Casual", "Resources": "Most",
                  "Raids": "MuchMore", "Portals": "Casual"},
    "keys": {"PlayerDamage": "100", "EnemyDamage": "150", "ResourceRate": "300",
             "SkillReductionRate": "0", "TeleportAll": "True",
             "DeathKeepInventory": "False", "DeathSkillsReset": "False"},
    "extra": {"MaxLevelIncrease": "2"},
}


@contextmanager
def lock():
    with open(os.path.join(BASE, ".lock"), "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def _read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def _write(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp, path)


def global_key_schema():
    """{KeyName: 'bool' | 'number'} parsed from the live ControlCenter config."""
    schema = {}
    text = _read(CC_CFG)
    m = re.search(r"^\[GlobalKeys\]\r?\n(.*?)(?=^\[|\Z)", text, re.S | re.M)
    block = m.group(1) if m else ""
    kind = "number"
    for line in block.splitlines():
        if line.startswith("# Acceptable values: NotSet, False, True"):
            kind = "bool"
        elif re.match(r"^[A-Za-z]+ = ", line):
            schema[line.split(" = ")[0]] = kind
            kind = "number"
    return schema


def all_settings():
    """{lowercase name: (canonical name, category, kind)}"""
    out = {}
    for k, kind in global_key_schema().items():
        out[k.lower()] = (k, "keys", kind)
    for k in MODIFIERS:
        out[k.lower()] = (k, "modifiers", "enum")
    for k in EXTRA:
        out[k.lower()] = (k, "extra", "number")
    return out


def value_choices(canonical, category, kind):
    if kind == "bool":
        return ["True", "False"]
    if kind == "enum":
        return MODIFIERS[canonical]
    return []


def normalize_value(canonical, category, kind, raw):
    raw = raw.strip()
    if kind == "bool":
        if raw.lower() in ("true", "on", "yes", "1"):
            return "True"
        if raw.lower() in ("false", "off", "no", "0"):
            return "False"
        raise ValueError(f"{canonical} must be True or False")
    if kind == "enum":
        for opt in MODIFIERS[canonical]:
            if opt.lower() == raw.lower().replace(" ", ""):
                return opt
        raise ValueError(f"{canonical} must be one of: {', '.join(MODIFIERS[canonical])}")
    if not re.fullmatch(r"\d{1,5}(\.\d{1,3})?", raw):
        raise ValueError(f"{canonical} must be a number (e.g. 150)")
    return raw


def list_worlds():
    names = set()
    if os.path.isdir(WORLDS_DIR):
        for e in os.listdir(WORLDS_DIR):
            p = os.path.join(WORLDS_DIR, e)
            if "_backup_" in e or e.endswith(".old"):
                continue
            if e.endswith(".fwl") and NAME_RE.match(e[:-4]) and os.path.getsize(p) > 100:
                names.add(e[:-4])
            elif os.path.isdir(p) and NAME_RE.match(e) and any(f.endswith(".fwl2") for f in os.listdir(p)):
                names.add(e)
    for e in os.listdir(PROFILES) if os.path.isdir(PROFILES) else []:
        if e.endswith(".json"):
            names.add(e[:-5])
    return sorted(names, key=str.lower)


def resolve_world(name):
    """Case-insensitive match against known worlds; returns canonical name or None."""
    for w in list_worlds():
        if w.lower() == name.lower():
            return w
    return None


def profile_path(world):
    return os.path.join(PROFILES, world + ".json")


def load_profile(world):
    try:
        with open(profile_path(world), encoding="utf-8") as f:
            p = json.load(f)
    except FileNotFoundError:
        p = json.loads(json.dumps(TEMPLATE))
    for k in TEMPLATE:
        p.setdefault(k, {})
    p.setdefault("description", "")
    return p


def save_profile(world, profile):
    os.makedirs(PROFILES, exist_ok=True)
    _write(profile_path(world), json.dumps(profile, indent=2) + "\n")


def get_active():
    try:
        with open(STATE, encoding="utf-8") as f:
            w = json.load(f).get("active")
            if w and NAME_RE.match(w):
                return w
    except (FileNotFoundError, ValueError):
        pass
    return DEFAULT_WORLD


def set_active(world):
    _write(STATE, json.dumps({"active": world}) + "\n")


def _set_cfg_value(text, section, key, value):
    m = re.search(rf"^\[{re.escape(section)}\]\r?\n(.*?)(?=^\[|\Z)", text, re.S | re.M)
    if not m:
        raise RuntimeError(f"section [{section}] not found")
    block = m.group(1)
    new_block, n = re.subn(rf"^{re.escape(key)} = [^\r\n]*", f"{key} = {value}", block, count=1, flags=re.M)
    if n == 0:
        raise RuntimeError(f"{key} not found in [{section}]")
    return text[:m.start(1)] + new_block + text[m.end(1):]


def apply_profile(world):
    """Write the profile into the mod configs. Unlisted global keys are reset to NotSet."""
    p = load_profile(world)
    cc = _read(CC_CFG)
    for k in global_key_schema():
        cc = _set_cfg_value(cc, "GlobalKeys", k, p["keys"].get(k, "NotSet"))
    cc = _set_cfg_value(cc, "WorldModifiers", "Preset", "-1")
    for k in MODIFIERS:
        cc = _set_cfg_value(cc, "WorldModifiers", k, p["modifiers"].get(k, "-1"))
    _write(CC_CFG, cc)
    for k, (path, section) in EXTRA.items():
        text = _read(path)
        text = _set_cfg_value(text, section, k, p["extra"].get(k, "0"))
        _write(path, text)


def modifier_flags(world):
    p = load_profile(world)
    parts = []
    for k, v in p["modifiers"].items():
        if k in MODIFIERS and v in MODIFIERS[k]:
            parts.append(f"-modifier {k.lower()} {v.lower()}")
    return " ".join(parts)


def players_online():
    """Player count from the most recent server log line, or 0 if unknown."""
    try:
        with open(LOG, errors="replace") as f:
            lines = f.readlines()[-3000:]
    except OSError:
        return 0
    n = 0
    for line in lines:
        m = re.search(r"now (\d+) player\(s\)", line)
        if m:
            n = int(m.group(1))
    return n


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "world":
        print(get_active())
    elif cmd == "modifiers":
        print(modifier_flags(get_active()))
    elif cmd == "apply":
        with lock():
            apply_profile(get_active())
    else:
        sys.exit(__doc__)
