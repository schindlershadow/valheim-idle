#!/bin/sh
# BepInEx-specific settings
# NOTE: Do not edit unless you know what you are doing!
####
export DOORSTOP_ENABLED=1
export DOORSTOP_TARGET_ASSEMBLY=./BepInEx/core/BepInEx.Preloader.dll

export LD_LIBRARY_PATH="./doorstop_libs:$LD_LIBRARY_PATH"
export LD_PRELOAD="libdoorstop_x64.so:$LD_PRELOAD"
####


export LD_LIBRARY_PATH="./linux64:$LD_LIBRARY_PATH"
export SteamAppId=892970

echo "Starting server PRESS CTRL-C to exit"

# Tip: Make a local copy of this script to avoid it being overwritten by steam.
# NOTE: Minimum password length is 5 characters & Password cant be in the server name.
# NOTE: You need to make sure the ports 2456-2458 is being forwarded to your server through your local router & firewall.



rm -f ./BepInEx/LogOutput.log
systemctl --user stop valheim-discord.service 2>/dev/null
systemd-run --user --quiet --collect --unit=valheim-discord --working-directory="$PWD" ./discord_notify.sh $$

# Server password: first line of ~/.config/valheim-discord/server_password (min 5 chars, not in server name)
PASSFILE="$HOME/.config/valheim-discord/server_password"
[ -r "$PASSFILE" ] || { echo "missing $PASSFILE" >&2; exit 1; }
SERVER_PASSWORD=$(head -n1 "$PASSFILE")
SERVER_NAME="${VALHEIM_SERVER_NAME:-My Valheim Server}"

PY=/usr/bin/python3
CTL="$HOME/valheim-idle/worldctl.py"
WORLD=$($PY "$CTL" world 2>/dev/null) || WORLD=${VALHEIM_DEFAULT_WORLD:-MyWorld}
MODS=$($PY "$CTL" modifiers 2>/dev/null)
$PY "$CTL" apply 2>/dev/null

# $MODS is generated from validated names and intentionally word-split
exec ./valheim_server.x86_64 -batchmode -nographics -job-worker-count 4 -name "$SERVER_NAME" -port 2456 -world "$WORLD" -password "$SERVER_PASSWORD" -crossplay $MODS
