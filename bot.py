"""
Discord GIF Bot - Headless version for 24/7 hosting (Railway, VPS, etc.)
--------------------------------------------------------------------------
Slash commands: /random, /gif, /gifs, /add, /addmany, /remove, /list,
                /search, /stats, /tagcount, /caption, /vote, /help

No GUI, no config.json with secrets - the bot token comes from an
environment variable (DISCORD_BOT_TOKEN), and the GIF list is stored
in gifs.json which lives alongside this script.

Requires: pip install -U discord.py
"""

import json
import os
import random

import discord
from discord import app_commands

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
GUILD_ID = os.environ.get("GUILD_ID")  # optional - instant sync to one server
DATA_FILE = "gifs.json"

if not TOKEN:
    raise RuntimeError(
        "DISCORD_BOT_TOKEN environment variable is not set. "
        "On Railway, add it under your service's Variables tab."
    )


# ---------------------------------------------------------------------------
# GIF storage (simple JSON file: list of {"url": ..., "tag": ...})
# ---------------------------------------------------------------------------

def load_gifs():
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save_gifs(gifs):
    with open(DATA_FILE, "w", encoding="utf8") as f:
        json.dump(gifs, f, indent=2)


gifs = load_gifs()


# ---------------------------------------------------------------------------
# Bot client
# ---------------------------------------------------------------------------

class GifBotClient(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        if GUILD_ID:
            guild_obj = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild_obj)
            await self.tree.sync(guild=guild_obj)
            print(f"Slash commands synced instantly to guild {GUILD_ID}.")
        else:
            await self.tree.sync()
            print("Slash commands synced globally (can take up to an hour to appear).")


client = GifBotClient()


@client.event
async def on_ready():
    print(f"Logged in as {client.user} (id: {client.user.id})")
    print(f"{len(gifs)} GIF(s) loaded.")


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------

@client.tree.command(name="random", description="Send a random GIF from the saved list")
async def random_cmd(interaction: discord.Interaction):
    if not gifs:
        await interaction.response.send_message("No GIFs saved yet. Use /add to add one.", ephemeral=True)
        return
    gif = random.choice(gifs)
    await interaction.response.send_message(gif["url"])


@client.tree.command(name="gif", description="Send a GIF that matches a tag")
@app_commands.describe(tag="Tag to search for")
async def gif_cmd(interaction: discord.Interaction, tag: str):
    matches = [g for g in gifs if tag.lower() in g.get("tag", "").lower()]
    if not matches:
        await interaction.response.send_message(f"No GIFs tagged '{tag}'.", ephemeral=True)
        return
    gif = random.choice(matches)
    await interaction.response.send_message(gif["url"])


@client.tree.command(name="gifs", description="List all saved tags")
async def gifs_cmd(interaction: discord.Interaction):
    tags = sorted({g.get("tag", "").strip() for g in gifs if g.get("tag", "").strip()})
    text = ", ".join(tags) if tags else "No tags saved yet."
    await interaction.response.send_message(f"Available tags: {text}", ephemeral=True)


@client.tree.command(name="add", description="Add a GIF by URL or by attaching a file")
@app_commands.describe(
    tag="Tag to file this GIF under (optional)",
    url="A direct GIF/image URL (optional if you attach a file instead)",
    attachment="Upload a GIF/image file directly (optional if you give a URL instead)",
)
async def add_cmd(
    interaction: discord.Interaction,
    tag: str = "",
    url: str = None,
    attachment: discord.Attachment = None,
):
    if not url and not attachment:
        await interaction.response.send_message(
            "Give me either a URL or attach a file.", ephemeral=True
        )
        return

    final_url = attachment.url if attachment else url.strip()

    # Basic sanity check so people don't accidentally add a random link
    if attachment and not (attachment.content_type or "").startswith(("image/", "video/")):
        await interaction.response.send_message(
            "That attachment doesn't look like an image or GIF.", ephemeral=True
        )
        return

    if any(g["url"] == final_url for g in gifs):
        await interaction.response.send_message("That GIF is already in the list.", ephemeral=True)
        return

    gifs.append({"url": final_url, "tag": tag.strip()})
    save_gifs(gifs)
    await interaction.response.send_message(f"Added! ({len(gifs)} total)")


@client.tree.command(name="remove", description="Remove a saved GIF by its number (see /list)")
@app_commands.describe(index="The number shown next to the GIF in /list")
async def remove_cmd(interaction: discord.Interaction, index: int):
    if index < 1 or index > len(gifs):
        await interaction.response.send_message(
            f"Pick a number between 1 and {len(gifs)}. Use /list to see them.", ephemeral=True
        )
        return
    removed = gifs.pop(index - 1)
    save_gifs(gifs)
    await interaction.response.send_message(f"Removed GIF #{index} ({removed['url'][:60]}).", ephemeral=True)


@client.tree.command(name="tag", description="Add a tag to an untagged GIF, or change its existing tag")
@app_commands.describe(
    index="The number shown next to the GIF in /list",
    tag="The new tag to set (leave blank to clear the tag)",
)
async def tag_cmd(interaction: discord.Interaction, index: int, tag: str = ""):
    if index < 1 or index > len(gifs):
        await interaction.response.send_message(
            f"Pick a number between 1 and {len(gifs)}. Use /list to see them.", ephemeral=True
        )
        return
    gif = gifs[index - 1]
    old_tag = gif.get("tag", "").strip()
    gif["tag"] = tag.strip()
    save_gifs(gifs)

    if tag.strip():
        msg = f"GIF #{index} tag set to '{tag.strip()}'" + (f" (was '{old_tag}')" if old_tag else "") + "."
    else:
        msg = f"GIF #{index} tag cleared."
    await interaction.response.send_message(msg, ephemeral=True)


@client.tree.command(name="list", description="List all saved GIFs with their numbers")
async def list_cmd(interaction: discord.Interaction):
    if not gifs:
        await interaction.response.send_message("No GIFs saved yet.", ephemeral=True)
        return
    lines = []
    for i, g in enumerate(gifs, start=1):
        tag = f" [{g['tag']}]" if g.get("tag") else ""
        lines.append(f"{i}.{tag} {g['url']}")
    # Discord messages cap at 2000 chars - trim if the list gets long
    text = "\n".join(lines)
    if len(text) > 1900:
        text = text[:1900] + "\n... (list truncated)"
    await interaction.response.send_message(text, ephemeral=True)


@client.tree.command(name="addmany", description="Add several GIF URLs at once (one per line)")
@app_commands.describe(
    urls="Paste multiple URLs, one per line (or separated by spaces)",
    tag="Tag to apply to all of them (optional)",
)
async def addmany_cmd(interaction: discord.Interaction, urls: str, tag: str = ""):
    candidates = [u.strip() for u in urls.replace(",", "\n").split() if u.strip()]
    if not candidates:
        await interaction.response.send_message("Didn't find any URLs in that.", ephemeral=True)
        return

    existing_urls = {g["url"] for g in gifs}
    added, skipped = 0, 0
    for u in candidates:
        if not u.startswith(("http://", "https://")):
            skipped += 1
            continue
        if u in existing_urls:
            skipped += 1
            continue
        gifs.append({"url": u, "tag": tag.strip()})
        existing_urls.add(u)
        added += 1

    save_gifs(gifs)
    await interaction.response.send_message(
        f"Added {added} GIF(s), skipped {skipped} (duplicates or invalid links). "
        f"Total: {len(gifs)}."
    )


@client.tree.command(name="search", description="Search saved GIFs by URL or tag text")
@app_commands.describe(query="Text to search for")
async def search_cmd(interaction: discord.Interaction, query: str):
    q = query.lower().strip()
    matches = [g for g in gifs if q in g["url"].lower() or q in g.get("tag", "").lower()]
    if not matches:
        await interaction.response.send_message(f"No matches for '{query}'.", ephemeral=True)
        return
    lines = []
    for g in matches[:15]:
        idx = gifs.index(g) + 1
        tag = f" [{g['tag']}]" if g.get("tag") else ""
        lines.append(f"{idx}.{tag} {g['url']}")
    extra = f"\n...and {len(matches) - 15} more" if len(matches) > 15 else ""
    await interaction.response.send_message(
        f"Found {len(matches)} match(es):\n" + "\n".join(lines) + extra, ephemeral=True
    )


@client.tree.command(name="stats", description="Show stats about the saved GIF collection")
async def stats_cmd(interaction: discord.Interaction):
    total = len(gifs)
    tagged = sum(1 for g in gifs if g.get("tag", "").strip())
    untagged = total - tagged
    tag_counts = {}
    for g in gifs:
        t = g.get("tag", "").strip()
        if t:
            tag_counts[t] = tag_counts.get(t, 0) + 1
    top = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    top_text = ", ".join(f"{name} ({count})" for name, count in top) if top else "none yet"

    embed = discord.Embed(title="GIF Collection Stats", color=discord.Color.blurple())
    embed.add_field(name="Total GIFs", value=str(total), inline=True)
    embed.add_field(name="Tagged", value=str(tagged), inline=True)
    embed.add_field(name="Untagged", value=str(untagged), inline=True)
    embed.add_field(name="Unique tags", value=str(len(tag_counts)), inline=True)
    embed.add_field(name="Top tags", value=top_text, inline=False)
    await interaction.response.send_message(embed=embed)


@client.tree.command(name="tagcount", description="Show how many GIFs each tag has")
async def tagcount_cmd(interaction: discord.Interaction):
    tag_counts = {}
    for g in gifs:
        t = g.get("tag", "").strip() or "(untagged)"
        tag_counts[t] = tag_counts.get(t, 0) + 1
    if not tag_counts:
        await interaction.response.send_message("No GIFs saved yet.", ephemeral=True)
        return
    lines = [f"{name}: {count}" for name, count in sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)]
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@client.tree.command(name="caption", description="Send a random (or tagged) GIF with your own caption")
@app_commands.describe(caption="Text to show above the GIF", tag="Only pick from GIFs with this tag (optional)")
async def caption_cmd(interaction: discord.Interaction, caption: str, tag: str = ""):
    pool = gifs
    if tag.strip():
        pool = [g for g in gifs if tag.lower() in g.get("tag", "").lower()]
    if not pool:
        await interaction.response.send_message("No matching GIFs to caption.", ephemeral=True)
        return
    gif = random.choice(pool)
    await interaction.response.send_message(f"{caption}\n{gif['url']}")


@client.tree.command(name="vote", description="Post a GIF with thumbs up/down reactions for the chat to vote on")
@app_commands.describe(tag="Only pick from GIFs with this tag (optional)")
async def vote_cmd(interaction: discord.Interaction, tag: str = ""):
    pool = gifs
    if tag.strip():
        pool = [g for g in gifs if tag.lower() in g.get("tag", "").lower()]
    if not pool:
        await interaction.response.send_message("No matching GIFs to vote on.", ephemeral=True)
        return
    gif = random.choice(pool)
    await interaction.response.send_message(f"Vote time!\n{gif['url']}")
    msg = await interaction.original_response()
    await msg.add_reaction("👍")
    await msg.add_reaction("👎")


@client.tree.command(name="help", description="Show all available commands")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="GIF Bot Commands",
        description="Here's everything I can do:",
        color=discord.Color.green(),
    )
    for cmd in sorted(client.tree.get_commands(), key=lambda c: c.name):
        params = ", ".join(f"{p.name}" for p in cmd.parameters) if cmd.parameters else "no options"
        embed.add_field(name=f"/{cmd.name}", value=f"{cmd.description}\n*({params})*", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


client.run(TOKEN)
