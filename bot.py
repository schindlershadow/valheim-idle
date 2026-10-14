#!/usr/bin/env python3
"""Discord bot: switch Valheim worlds and edit per-world settings."""
import asyncio
import os
import subprocess

import discord
from discord import app_commands

import worldctl as wc

TOKEN = open(os.path.expanduser("~/.config/valheim-discord/bot_token")).read().strip()
SERVICE = "valheim.service"
lock = asyncio.Lock()


def sh(*args):
    return subprocess.run(args, capture_output=True, text=True).stdout.strip()


def server_active():
    return sh("systemctl", "--user", "is-active", SERVICE) == "active"


def fmt_profile(world):
    p = wc.load_profile(world)
    lines = [p["description"]] if p["description"] else []
    lines += [f"**Modifiers:** " + (", ".join(f"{k}={v}" for k, v in sorted(p["modifiers"].items())) or "none")]
    lines.append("**Keys:** " + (", ".join(f"{k}={v}" for k, v in sorted(p["keys"].items())) or "none"))
    if p["extra"]:
        lines.append("**Other:** " + ", ".join(f"{k}={v}" for k, v in sorted(p["extra"].items())))
    return "\n".join(lines)


async def restart_server():
    await asyncio.to_thread(subprocess.run, ["systemctl", "--user", "restart", "--no-block", SERVICE])


async def guard_players(inter, force):
    """Returns True if the action must be refused (and replies)."""
    if server_active() and not force:
        n = wc.players_online()
        if n > 0:
            await inter.followup.send(
                f"{n} player(s) are online. Re-run with `force: True` to restart anyway.")
            return True
    return False


intents = discord.Intents.none()
intents.guilds = True
client = discord.Client(intents=intents, allowed_mentions=discord.AllowedMentions.none())
tree = app_commands.CommandTree(client)

world_group = app_commands.Group(name="world", description="Switch or create worlds")
setting_group = app_commands.Group(name="setting", description="View or change world settings")
server_group = app_commands.Group(name="server", description="Server status and control")


async def world_ac(inter, current):
    cur = current.lower()
    return [app_commands.Choice(name=w, value=w) for w in wc.list_worlds() if cur in w.lower()][:25]


async def setting_ac(inter, current):
    cur = current.lower()
    return [app_commands.Choice(name=c, value=c) for _, (c, _, _) in sorted(wc.all_settings().items())
            if cur in c.lower()][:25]


async def value_ac(inter, current):
    key = (inter.namespace.setting or "").lower()
    info = wc.all_settings().get(key)
    if not info:
        return []
    choices = wc.value_choices(*info)
    if info[2] == "number":
        tmpl = wc.TEMPLATE["keys"].get(info[0]) or wc.TEMPLATE["extra"].get(info[0])
        choices = [current] if current else ([tmpl] if tmpl else ["100"])
    return [app_commands.Choice(name=c, value=c) for c in choices if current.lower() in c.lower()][:25]


@world_group.command(name="list", description="List worlds and show the active one")
async def world_list(inter: discord.Interaction):
    active = wc.get_active()
    lines = []
    for w in wc.list_worlds():
        d = wc.load_profile(w)["description"]
        lines.append((f"**{w}** (active)" if w == active else w) + (f" - {d}" if d else ""))
    await inter.response.send_message("Worlds:\n" + "\n".join(lines))


@world_group.command(name="set", description="Switch the server to another world")
@app_commands.describe(name="World to switch to", force="Switch even if players are online")
@app_commands.autocomplete(name=world_ac)
async def world_set(inter: discord.Interaction, name: str, force: bool = False):
    await inter.response.defer()
    world = wc.resolve_world(name)
    if not world:
        return await inter.followup.send(f"No world named `{name}`. Use `/world create` to make one.")
    await switch(inter, world, force, created=False)


@world_group.command(name="create", description="Create a new world and switch to it")
@app_commands.describe(name="Name for the new world (letters, numbers, - and _)",
                       description="Optional description", force="Switch even if players are online")
async def world_create(inter: discord.Interaction, name: str, description: str = "", force: bool = False):
    await inter.response.defer()
    if not wc.NAME_RE.match(name):
        return await inter.followup.send("Names can only use letters, numbers, `-` and `_` (max 30).")
    if wc.resolve_world(name):
        return await inter.followup.send(f"`{name}` already exists. Use `/world set`.")
    await switch(inter, name, force, created=True, description=" ".join(description.split())[:200])


async def switch(inter, world, force, created, description=""):
    async with lock:
        if await guard_players(inter, force):
            return
        was_active = server_active()
        if created:
            p = wc.load_profile(world)
            p["description"] = description
            wc.save_profile(world, p)
        wc.set_active(world)
        wc.apply_profile(world)
        if was_active:
            await restart_server()
            tail = "Restarting the server now; it will be back in a minute or two."
        else:
            tail = "The server is asleep; it will load this world the next time it wakes up."
        verb = "Created and switched to" if created else "Switched to"
        await inter.followup.send(f"{verb} **{world}**. {tail}\n{fmt_profile(world)}")


@world_group.command(name="describe", description="Set a world's description (empty to clear)")
@app_commands.describe(name="World to describe", description="What this world is / how it plays")
@app_commands.autocomplete(name=world_ac)
async def world_describe(inter: discord.Interaction, name: str, description: str = ""):
    world = wc.resolve_world(name)
    if not world:
        return await inter.response.send_message(f"No world named `{name}`.")
    description = " ".join(description.split())
    if len(description) > 200:
        return await inter.response.send_message("Descriptions are limited to 200 characters.")
    async with lock:
        p = wc.load_profile(world)
        p["description"] = description
        wc.save_profile(world, p)
    await inter.response.send_message(
        f"**{world}**: " + (f"description set to \"{description}\"." if description else "description cleared."))


@setting_group.command(name="show", description="Show a world's settings")
@app_commands.describe(world="World (default: active world)")
@app_commands.autocomplete(world=world_ac)
async def setting_show(inter: discord.Interaction, world: str | None = None):
    w = wc.resolve_world(world) if world else wc.get_active()
    if not w:
        return await inter.response.send_message(f"No world named `{world}`.")
    await inter.response.send_message(f"Settings for **{w}**:\n{fmt_profile(w)}")


@setting_group.command(name="set", description="Change a setting in a world's profile")
@app_commands.describe(setting="Setting to change", value="New value", world="World (default: active world)")
@app_commands.autocomplete(setting=setting_ac, value=value_ac, world=world_ac)
async def setting_set(inter: discord.Interaction, setting: str, value: str, world: str | None = None):
    await change(inter, setting, value, world)


@setting_group.command(name="reset", description="Remove a setting from a world's profile (back to vanilla)")
@app_commands.describe(setting="Setting to reset", world="World (default: active world)")
@app_commands.autocomplete(setting=setting_ac, world=world_ac)
async def setting_reset(inter: discord.Interaction, setting: str, world: str | None = None):
    await change(inter, setting, None, world)


async def change(inter, setting, value, world):
    w = wc.resolve_world(world) if world else wc.get_active()
    if not w:
        return await inter.response.send_message(f"No world named `{world}`.")
    info = wc.all_settings().get(setting.lower())
    if not info:
        return await inter.response.send_message(f"Unknown setting `{setting}`. Use autocomplete to pick one.")
    canonical, category, kind = info
    try:
        new = wc.normalize_value(canonical, category, kind, value) if value is not None else None
    except ValueError as e:
        return await inter.response.send_message(str(e))
    async with lock:
        p = wc.load_profile(w)
        if new is None:
            p[category].pop(canonical, None)
        else:
            p[category][canonical] = new
        wc.save_profile(w, p)
        live = w == wc.get_active()
        if live:
            wc.apply_profile(w)
    what = f"{canonical} = {new}" if new is not None else f"{canonical} reset"
    if not live:
        note = "Saved to this world's profile; it applies when you switch to it."
    elif category == "keys":
        note = "Applied to the running server (config reloads automatically)."
    else:
        note = "Saved. This one needs a server restart to take effect (`/server restart`)."
    await inter.response.send_message(f"**{w}**: {what}. {note}")


@server_group.command(name="status", description="Show server state and active world")
async def server_status(inter: discord.Interaction):
    state = "online" if server_active() else "asleep (starts when someone tries to join)"
    n = wc.players_online() if server_active() else 0
    await inter.response.send_message(f"Server is {state}. Active world: **{wc.get_active()}**. Players: {n}.")


@server_group.command(name="start", description="Wake the server")
async def server_start(inter: discord.Interaction):
    if server_active():
        return await inter.response.send_message("Already running.")
    await asyncio.to_thread(subprocess.run, ["systemctl", "--user", "start", "--no-block", SERVICE])
    await inter.response.send_message("Starting the server...")


@server_group.command(name="restart", description="Restart the server (applies modifier changes)")
@app_commands.describe(force="Restart even if players are online")
async def server_restart(inter: discord.Interaction, force: bool = False):
    await inter.response.defer()
    async with lock:
        if await guard_players(inter, force):
            return
        wc.apply_profile(wc.get_active())
        await restart_server()
    await inter.followup.send("Restarting the server...")


for g in (world_group, setting_group, server_group):
    tree.add_command(g)


async def sync_guild(guild):
    tree.copy_global_to(guild=guild)
    await tree.sync(guild=guild)


@client.event
async def on_ready():
    await tree.sync()
    for guild in client.guilds:
        await sync_guild(guild)
    print(f"ready as {client.user}, synced to {len(client.guilds)} guild(s)", flush=True)


@client.event
async def on_guild_join(guild):
    await sync_guild(guild)
    print(f"joined {guild.name}, synced commands", flush=True)


@tree.error
async def on_error(inter: discord.Interaction, error):
    print(f"command error: {error!r}", flush=True)
    msg = "Something went wrong running that command."
    if inter.response.is_done():
        await inter.followup.send(msg)
    else:
        await inter.response.send_message(msg)


client.run(TOKEN)
