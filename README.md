# valheim-idle

Run a modded (BepInEx) Valheim dedicated server on a home Linux box that **sleeps when empty and wakes when someone tries to join**, with a Discord bot to switch worlds and tweak per-world settings.

| File | Purpose |
|---|---|
| `start.sh` | Server launcher (used by `valheim.service`); applies the active world's profile, then starts Valheim |
| `wake.py` | Holds UDP 2456-2458 while the server is stopped; first join packet (or a Wake-on-LAN packet to UDP 2459) starts it |
| `idle-check.py` | Run by a timer; stops the server after N minutes with no players |
| `worldctl.py` | Per-world profiles (`profiles/*.json`) written into the ServersideQoL ControlCenter / CreatureLevelUp configs and `-modifier` launch flags |
| `bot.py` | Discord slash-command bot: `/world list|set|create|describe`, `/setting show|set|reset`, `/server status|start|restart` |
| `discord_notify.sh` | Posts start/stop/join/leave/error messages to a Discord webhook |
| `systemd/` | User units wiring it all together |

## Requirements

- Linux with systemd user services (`loginctl enable-linger $USER` so they run without a login)
- Valheim dedicated server (Steam app 892970) with [BepInEx](https://valheim.thunderstore.io/package/denikson/BepInExPack_Valheim/) and the [ServersideQoL](https://thunderstore.io/c/valheim/p/ArgusMagnus/ServersideQoL/) mod (its ControlCenter and CreatureLevelUp configs must exist; run the server once to generate them)
- Python 3.10+, `curl`, `jq`

## Setup

1. **Clone to `~/valheim-idle`** (the unit files assume this path) and install the bot dependency:
   ```sh
   git clone <this repo> ~/valheim-idle && cd ~/valheim-idle
   python3 -m venv venv && venv/bin/pip install -r requirements.txt
   ```
2. **Install the server** to `~/valheim-server` (or elsewhere; then change `VALHEIM_SERVER_DIR` in the `systemd/*.service` files). Copy `discord_notify.sh` into that directory and `chmod +x` it.
3. **Secrets** (kept outside the repo, in `~/.config/valheim-discord/`; `chmod 600` them):
   ```sh
   mkdir -p ~/.config/valheim-discord && chmod 700 ~/.config/valheim-discord
   echo 'https://discord.com/api/webhooks/...' > ~/.config/valheim-discord/webhook_url   # channel webhook for notifications
   echo 'YOUR_BOT_TOKEN'                       > ~/.config/valheim-discord/bot_token     # from the Discord developer portal
   echo 'a-server-password'                    > ~/.config/valheim-discord/server_password  # >= 5 chars, not part of server name
   chmod 600 ~/.config/valheim-discord/*
   ```
   Create the bot at <https://discord.com/developers/applications>, then invite it with the `bot` and `applications.commands` scopes. No privileged intents are needed.
4. **Configure** via environment (edit the `Environment=` lines in the unit files, or add `Environment=` entries):
   - `VALHEIM_SERVER_DIR` - server install dir (default `~/valheim-server`)
   - `VALHEIM_SERVER_NAME` - name shown in the server browser and Discord messages
   - `VALHEIM_DEFAULT_WORLD` - world used before the bot has picked one
   - `IDLE_MIN` / `GRACE_MIN` - idle minutes before shutdown / startup grace (defaults 20 / 15)
5. **Install the units and start:**
   ```sh
   mkdir -p ~/.config/systemd/user && cp systemd/* ~/.config/systemd/user/
   systemctl --user daemon-reload
   systemctl --user enable --now valheim-wake.service valheim-idle.timer valheim-bot.service
   ```
   `valheim.service` is started on demand by the wake listener; after it stops, the listener takes the ports back.
6. **Forward UDP 2456-2458** on your router to the host.

## Profiles

`profiles/<World>.json` holds the world's modifiers (`-modifier` flags), ControlCenter global keys, and extras. Worlds without a profile use the template in `worldctl.py`. The bot edits these files; `state.json` (the active world) is created at runtime and ignored by git.

## Optional: wake button

Any tool that can send a Wake-on-LAN magic packet with MAC `02:56:4c:48:00:01` to UDP port 2459 on the host (e.g. a Home Assistant `wake_on_lan.send_magic_packet` button) will wake the server.

## Security notes

- Never commit anything from `~/.config/valheim-discord/`. The webhook URL and bot token grant control of your Discord channel/bot; rotate them if they leak.
- Bot commands are available to anyone in the guild where it is installed. Restrict them with Discord's *Server Settings > Integrations* command permissions.
