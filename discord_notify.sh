#!/bin/bash
# Usage: discord_notify.sh <server_pid>
# Watches BepInEx/LogOutput.log and posts server status to Discord.
PID="$1"
DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$DIR/BepInEx/LogOutput.log"
URL="$(cat "$HOME/.config/valheim-discord/webhook_url")"

post() {
  jq -n --arg c "$1" '{content:$c}' | curl -s -o /dev/null -H 'Content-Type: application/json' -d @- "$URL"
}

[ -n "$NOSTART" ] || post ":hourglass_flowing_sand: **${VALHEIM_SERVER_NAME:-My Valheim Server}** is starting up..."

ready=0; clean=0; last_err=0; suppressed=0

report_error() {
  local now; now=$(date +%s)
  if (( now - last_err < 60 )); then suppressed=$((suppressed+1)); return; fi
  local extra=""; (( suppressed > 0 )) && extra=" (+$suppressed similar suppressed)"
  suppressed=0; last_err=$now
  local msg=${1//\`/\'}
  post ":rotating_light: **Server error**$extra"$'\n'"\`\`\`${msg:0:400}\`\`\`"
}

tail -n 0 -F --pid="$PID" "$LOG" 2>/dev/null | while IFS= read -r line; do
  case "$line" in
    *"is active with"*"player(s)"*)
      ready=1
      code=$(sed -n 's/.*join code \([0-9]*\).*/\1/p' <<<"$line")
      post ":white_check_mark: **${VALHEIM_SERVER_NAME:-My Valheim Server}** is online and ready! Join code: \`$code\`" ;;
    *"Player connection lost server"*)
      n=$(sed -n 's/.*now \([0-9]*\) player(s).*/\1/p' <<<"$line")
      post ":wave: A player left the server (${n:-?} online)" ;;
    *"Network version check, their:"*)
      their=$(sed -n 's/.*their:\([0-9]*\),.*/\1/p' <<<"$line"); mine=$(sed -n 's/.*mine:\([0-9]*\).*/\1/p' <<<"$line")
      [ "$their" != "$mine" ] && post ":warning: A player was rejected: game version mismatch (theirs: $their, server: $mine). They need to update Valheim." ;;
    *"Steam manager on destroy"*|*"Net scene destroyed"*)
      clean=1 ;;
    *"Unhandled Exception"*|*"Fatal"*"Unity Log"*|*"Crash!!!"*|*"SIGSEGV"*)
      report_error "$line" ;;
    "[Error"*)
      (( ready )) || continue
      case "$line" in
        *"Failed to play intro"*|*"AsyncResourceUpload"*|*"video decode"*|*"render path shader"*|*"graphics config"*) continue ;;
      esac
      report_error "$line" ;;
    *"Got handshake from client"*)
      post ":electric_plug: Connection detected, a player is connecting..." ;;
    *"Got character ZDOID from"*)
      name=$(sed -n 's/.*Got character ZDOID from \(.*\) : -\?[0-9]*:[0-9]*$/\1/p' <<<"$line")
      [ -n "$name" ] && [ "$name" != "$line" ] && post ":bust_in_silhouette: **$name** joined the server" ;;
  esac
done

sleep 3
res=$(systemctl --user show valheim.service -p Result --value 2>/dev/null)
[ "$res" = "success" ] && clean=1
[ -n "$res" ] && [ "$res" != "success" ] && clean=0
if (( clean )); then
  post ":octagonal_sign: **${VALHEIM_SERVER_NAME:-My Valheim Server}** has shut down."
else
  post ":skull: **${VALHEIM_SERVER_NAME:-My Valheim Server}** stopped unexpectedly (crash or killed). Check the logs."
fi
