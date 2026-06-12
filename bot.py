import discord
from discord.ext import commands
import os
import datetime
import json
import asyncio
import yt_dlp
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv

load_dotenv()

# ============================================================
#  CONFIG
# ============================================================
TOKEN                = os.getenv("DISCORD_TOKEN")
WELCOME_CHANNEL_NAME = "💬・general-chat"
LEAVE_CHANNEL_NAME   = "🤖・server-logs"
BOOST_CHANNEL_NAME   = "🤖・server-logs"
MOD_ROLES = ["Admin", "EC Mod", "EC Team"]
MUTED_ROLE_NAME      = "Muted"
MODLOG_CHANNEL_NAME  = "🤖・server-logs"
TIMEOUT_ROLES = ["EC Mod"]  # roles that can only timeout/untimeout

SPOTIFY_CLIENT_ID     = os.getenv("SPOTIFY_CLIENT_ID", "8d7d5d56649548068d927a6e17fa5856")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "d4ea0417c9684e18bc8086a24c3e2764")

sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET
))

# ============================================================
#  DATA FILES
# ============================================================
WARNINGS_FILE  = "warnings.json"
MSG_COUNT_FILE = "message_counts.json"
INVITES_FILE   = "invites.json"
AR_FILE        = "auto_responses.json"
MODLOG_FILE    = "modlogs.json"

AUTO_RESPONSES = {}

def load_json(filename):
    if os.path.exists(filename):
        with open(filename, "r") as f:
            return json.load(f)
    return {}

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)

def extract_spotify_query(url):
    """Extract song name + artist from Spotify URL using API"""
    try:
        if "track" in url:
            track_id = url.split("track/")[1].split("?")[0]
            track    = sp.track(track_id)
            name     = track["name"]
            artist   = track["artists"][0]["name"]
            return f"{name} {artist}"
        elif "playlist" in url:
            return None, "playlist"
        else:
            return None, "unsupported"
    except Exception as e:
        return None

# ============================================================
#  MODLOG HELPER
# ============================================================
async def send_modlog(guild, action, moderator, target, reason, duration):
    logs = load_json(MODLOG_FILE)
    gid  = str(guild.id)
    uid  = str(target.id)
    if gid not in logs: logs[gid] = {}
    if uid not in logs[gid]: logs[gid][uid] = []
    logs[gid][uid].append({
        "action"   : action,
        "moderator": moderator.name,
        "reason"   : reason,
        "duration" : duration,
        "timestamp": str(datetime.datetime.utcnow())
    })
    save_json(MODLOG_FILE, logs)
    channel = discord.utils.get(guild.text_channels, name=MODLOG_CHANNEL_NAME)
    if not channel:
        return
    colors = {
        "Mute": discord.Color.orange(), "Unmute": discord.Color.green(),
        "Ban": discord.Color.red(), "Kick": discord.Color.dark_orange(),
        "Timeout": discord.Color.gold(), "Timeout Removed": discord.Color.green(),
        "Warn": discord.Color.yellow(),
    }
    embed = discord.Embed(title=f"🔨 Mod Action — {action}", color=colors.get(action, discord.Color.blurple()), timestamp=datetime.datetime.utcnow())
    embed.add_field(name="Moderator", value=f"{moderator.mention} (`{moderator.name}`)", inline=True)
    embed.add_field(name="Target",    value=f"{target.mention} (`{target.name}`)",       inline=True)
    embed.add_field(name="Reason",    value=reason,   inline=False)
    embed.add_field(name="Duration",  value=duration, inline=True)
    embed.set_footer(text=f"Target ID: {target.id}")
    await channel.send(embed=embed)

# ============================================================
#  INTENTS
# ============================================================
intents = discord.Intents.default()
intents.members         = True
intents.message_content = True
intents.invites         = True

bot = commands.Bot(command_prefix="!", intents=intents)

invite_cache = {}
music_queues = {}

# ============================================================
#  READY
# ============================================================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")
    for guild in bot.guilds:
        try:
            invites = await guild.fetch_invites()
            invite_cache[guild.id] = {inv.code: inv.uses for inv in invites}
        except Exception:
            pass

# ============================================================
#  PERMISSION CHECK
# ============================================================
def has_mod_role():
    async def predicate(ctx):
        return any(role.name in MOD_ROLES for role in ctx.author.roles)
    return commands.check(predicate)

# ============================================================
#  WELCOME
# ============================================================
@bot.event
async def on_member_join(member):
    guild = member.guild
    inviter = None
    try:
        new_invites = await guild.fetch_invites()
        old_cache   = invite_cache.get(guild.id, {})
        for inv in new_invites:
            if old_cache.get(inv.code, 0) < inv.uses:
                inviter = inv.inviter
                break
        invite_cache[guild.id] = {inv.code: inv.uses for inv in new_invites}
        if inviter:
            invite_data = load_json(INVITES_FILE)
            gid = str(guild.id)
            uid = str(inviter.id)
            if gid not in invite_data: invite_data[gid] = {}
            invite_data[gid][uid] = invite_data[gid].get(uid, 0) + 1
            save_json(INVITES_FILE, invite_data)
    except Exception:
        pass
    channel = discord.utils.get(guild.text_channels, name=WELCOME_CHANNEL_NAME)
    if channel:
        signup_channel = discord.utils.get(guild.text_channels, name="⚜️-glitchy-sign-up")
        signup_mention = signup_channel.mention if signup_channel else "#⚜️-glitchy-sign-up"
        embed = discord.Embed(
    title       = f"Welcome To Exposure Club {member.name}!",
    description = (
        f"Hey {member.mention}, you are member **#{guild.member_count}**\n\n"
        f"Check {signup_mention} to get **$10 bonus** on starting up! 💰"
    ),
    color     = discord.Color.green(),
    timestamp = datetime.datetime.utcnow()
)
        embed.set_thumbnail(url=member.display_avatar.url)
        await channel.send(embed=embed)

@bot.event
async def on_member_remove(member):
    channel = discord.utils.get(member.guild.text_channels, name=LEAVE_CHANNEL_NAME)
    if channel:
        await channel.send(f"👋 **{member.name}** has left the server. We now have **{member.guild.member_count}** members.")

@bot.event
async def on_member_update(before, after):
    if before.premium_since is None and after.premium_since is not None:
        channel = discord.utils.get(after.guild.text_channels, name=BOOST_CHANNEL_NAME)
        if channel:
            embed = discord.Embed(title="💜 New Server Booster!", description=f"Thank you **{after.mention}** for boosting! 🚀", color=discord.Color.purple(), timestamp=datetime.datetime.utcnow())
            embed.set_thumbnail(url=after.display_avatar.url)
            await channel.send(embed=embed)

# ============================================================
#  MESSAGE COUNT + AUTO RESPONSE
# ============================================================
@bot.event
async def on_message(message):
    if message.author.bot:
        await bot.process_commands(message)
        return
    data = load_json(MSG_COUNT_FILE)
    gid  = str(message.guild.id) if message.guild else None
    uid  = str(message.author.id)
    if gid:
        if gid not in data: data[gid] = {}
        data[gid][uid] = data[gid].get(uid, 0) + 1
        save_json(MSG_COUNT_FILE, data)
    if message.guild:
        content_lower = message.content.lower()
        ar_data  = load_json(AR_FILE)
        guild_ar = ar_data.get(str(message.guild.id), {})
        responded = False
        for trigger, response in guild_ar.items():
            if trigger in content_lower:
                await message.channel.send(response)
                responded = True
                break
        if not responded:
            for trigger, response in AUTO_RESPONSES.items():
                if trigger in content_lower:
                    await message.channel.send(response)
                    break
    await bot.process_commands(message)

# ============================================================
#  AUTO RESPONDER
# ============================================================
@bot.group(invoke_without_command=True)
async def ar(ctx):
    await ctx.send("Usage: `!ar add <trigger> <response>` | `!ar remove <trigger>` | `!ar list`")

@ar.command(name="add")
@has_mod_role()
async def ar_add(ctx, trigger: str, *, response: str):
    ar_data = load_json(AR_FILE)
    gid     = str(ctx.guild.id)
    if gid not in ar_data: ar_data[gid] = {}
    ar_data[gid][trigger.lower()] = response
    save_json(AR_FILE, ar_data)
    await ctx.send(f"✅ Trigger `{trigger.lower()}` added.")

@ar.command(name="remove")
@has_mod_role()
async def ar_remove(ctx, trigger: str):
    ar_data = load_json(AR_FILE)
    gid     = str(ctx.guild.id)
    trigger = trigger.lower()
    if gid in ar_data and trigger in ar_data[gid]:
        removed = ar_data[gid].pop(trigger)
        save_json(AR_FILE, ar_data)
        await ctx.send(f"✅ {removed}\nTrigger removed.")
    else:
        await ctx.send(f"❌ Trigger `{trigger}` not found.")

@ar.command(name="list")
async def ar_list(ctx):
    ar_data  = load_json(AR_FILE)
    guild_ar = ar_data.get(str(ctx.guild.id), {})
    if not guild_ar:
        await ctx.send("No custom auto-responses set yet.")
        return
    embed = discord.Embed(title="📋 Auto Responses", color=discord.Color.blurple())
    for trigger, response in guild_ar.items():
        embed.add_field(name=f"`{trigger}`", value=response, inline=False)
    await ctx.send(embed=embed)

# ============================================================
#  MUSIC
# ============================================================
YDL_OPTIONS = {
    "format"         : "bestaudio/best",
    "noplaylist"     : True,
    "quiet"          : True,
    "default_search" : "scsearch",
    "source_address" : "0.0.0.0",
    "prefer_ffmpeg"  : True,
}
FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options"       : "-vn -b:a 320k",
}

async def play_next(ctx):
    gid = ctx.guild.id
    if music_queues.get(gid):
        next_song = music_queues[gid].pop(0)
        source = await discord.FFmpegOpusAudio.from_probe(next_song["url"], **FFMPEG_OPTIONS)
        ctx.voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop))
        await ctx.send(f"🎵 Now playing: **{next_song['title']}**")
    else:
        await ctx.send("✅ Queue finished.")

@bot.command()
async def play(ctx, *, query: str):
    if not ctx.author.voice:
        await ctx.send("❌ You need to be in a voice channel first!")
        return
    vc = ctx.voice_client
    if not vc:
        vc = await ctx.author.voice.channel.connect()
    elif vc.channel != ctx.author.voice.channel:
        await vc.move_to(ctx.author.voice.channel)

    # Detect Spotify link and convert to search query
    if "open.spotify.com/track" in query:
        await ctx.send("🎵 Spotify link detected, finding song...")
        search_query = extract_spotify_query(query)
        if not search_query:
            await ctx.send("❌ Could not extract song info from Spotify link.")
            return
        await ctx.send(f"🔍 Searching SoundCloud for: **{search_query}**...")
    else:
        search_query = query
        await ctx.send(f"🔍 Searching for: **{query}**...")

    loop = asyncio.get_event_loop()
    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        try:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(search_query, download=False))
            if "entries" in info: info = info["entries"][0]
            url   = info["url"]
            title = info.get("title", "Unknown")
        except Exception as e:
            await ctx.send(f"❌ Could not find/play that.\n`{e}`")
            return

    gid = ctx.guild.id
    if gid not in music_queues: music_queues[gid] = []
    if vc.is_playing() or vc.is_paused():
        music_queues[gid].append({"url": url, "title": title})
        await ctx.send(f"➕ Added to queue: **{title}** (position #{len(music_queues[gid])})")
    else:
        music_queues[gid].insert(0, {"url": url, "title": title})
        await play_next(ctx)

@bot.command()
async def skip(ctx):
    vc = ctx.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await ctx.send("⏭️ Skipped.")
    else:
        await ctx.send("❌ Nothing is playing.")

@bot.command()
async def stop(ctx):
    music_queues[ctx.guild.id] = []
    vc = ctx.voice_client
    if vc:
        await vc.disconnect()
        await ctx.send("⏹️ Stopped and left the voice channel.")
    else:
        await ctx.send("❌ Not in a voice channel.")

@bot.command()
async def queue(ctx):
    q = music_queues.get(ctx.guild.id, [])
    if not q:
        await ctx.send("📭 Queue is empty.")
        return
    embed = discord.Embed(title="🎶 Music Queue", color=discord.Color.blurple())
    for i, song in enumerate(q, 1):
        embed.add_field(name=f"#{i}", value=song["title"], inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def nowplaying(ctx):
    vc = ctx.voice_client
    if vc and vc.is_playing():
        await ctx.send("🎵 A song is currently playing. Use `!queue` to see what's next.")
    else:
        await ctx.send("❌ Nothing is playing right now.")

# ============================================================
#  SERVER & MEMBER COMMANDS
# ============================================================
@bot.command()
async def membercount(ctx):
    await ctx.send(f"👥 Total members: **{ctx.guild.member_count}**")

@bot.command()
async def memberinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    roles  = [r.mention for r in member.roles if r.name != "@everyone"]
    embed  = discord.Embed(title=f"Member Info — {member.name}", color=member.color, timestamp=datetime.datetime.utcnow())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="ID",              value=member.id,                              inline=True)
    embed.add_field(name="Nickname",        value=member.nick or "None",                  inline=True)
    embed.add_field(name="Joined Server",   value=member.joined_at.strftime("%Y-%m-%d"),  inline=True)
    embed.add_field(name="Account Created", value=member.created_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name="Roles",           value=" ".join(roles) if roles else "None",   inline=False)
    warn_count = len(load_json(WARNINGS_FILE).get(str(ctx.guild.id), {}).get(str(member.id), []))
    embed.add_field(name="Warnings", value=str(warn_count), inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def serverinfo(ctx):
    guild = ctx.guild
    embed = discord.Embed(title=guild.name, color=discord.Color.blurple(), timestamp=datetime.datetime.utcnow())
    if guild.icon: embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="Owner",    value=guild.owner.mention,                  inline=True)
    embed.add_field(name="Members",  value=guild.member_count,                   inline=True)
    embed.add_field(name="Channels", value=len(guild.channels),                  inline=True)
    embed.add_field(name="Roles",    value=len(guild.roles),                     inline=True)
    embed.add_field(name="Boosts",   value=guild.premium_subscription_count,     inline=True)
    embed.add_field(name="Created",  value=guild.created_at.strftime("%Y-%m-%d"),inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def accountage(ctx, member: discord.Member = None):
    member = member or ctx.author
    age    = (datetime.datetime.utcnow() - member.created_at.replace(tzinfo=None)).days
    await ctx.send(f"🗓️ **{member.name}**'s account was created on **{member.created_at.strftime('%B %d, %Y')}** ({age // 365}y {(age % 365) // 30}m {age % 30}d ago).")

@bot.command()
async def invites(ctx, member: discord.Member = None):
    member = member or ctx.author
    count  = load_json(INVITES_FILE).get(str(ctx.guild.id), {}).get(str(member.id), 0)
    await ctx.send(f"📨 **{member.name}** has invited **{count}** member(s).")

@bot.command()
async def leaderboard(ctx):
    data = load_json(MSG_COUNT_FILE)
    gid  = str(ctx.guild.id)
    if gid not in data or not data[gid]:
        await ctx.send("No message data yet!")
        return
    sorted_members = sorted(data[gid].items(), key=lambda x: x[1], reverse=True)[:10]
    embed = discord.Embed(title=f"🏆 Most Active — {ctx.guild.name}", color=discord.Color.gold(), timestamp=datetime.datetime.utcnow())
    for rank, (uid, count) in enumerate(sorted_members, 1):
        member = ctx.guild.get_member(int(uid))
        name   = member.name if member else f"Unknown ({uid})"
        medal  = ["🥇","🥈","🥉"][rank-1] if rank <= 3 else f"#{rank}"
        embed.add_field(name=f"{medal} {name}", value=f"{count} messages", inline=False)
    await ctx.send(embed=embed)

# ============================================================
#  MOD COMMANDS
# ============================================================
@bot.command()
@has_mod_role()
async def mute(ctx, member: discord.Member, *, reason="No reason provided"):
    muted_role = discord.utils.get(ctx.guild.roles, name=MUTED_ROLE_NAME)
    if not muted_role:
        await ctx.send(f"❌ No role named **{MUTED_ROLE_NAME}** found.")
        return
    await member.add_roles(muted_role, reason=reason)
    await ctx.send(f"🔇 {member.mention} has been muted. Reason: {reason}")
    await send_modlog(ctx.guild, "Mute", ctx.author, member, reason, "Until unmuted")

@bot.command()
@has_mod_role()
async def unmute(ctx, member: discord.Member):
    muted_role = discord.utils.get(ctx.guild.roles, name=MUTED_ROLE_NAME)
    if not muted_role:
        await ctx.send(f"❌ No role named **{MUTED_ROLE_NAME}** found.")
        return
    await member.remove_roles(muted_role)
    await ctx.send(f"🔊 {member.mention} has been unmuted.")
    await send_modlog(ctx.guild, "Unmute", ctx.author, member, "N/A", "N/A")

@bot.command()
@has_mod_role()
async def warn(ctx, member: discord.Member, *, reason="No reason provided"):
    warnings = load_json(WARNINGS_FILE)
    gid, uid = str(ctx.guild.id), str(member.id)
    if gid not in warnings: warnings[gid] = {}
    if uid not in warnings[gid]: warnings[gid][uid] = []
    warnings[gid][uid].append({"reason": reason, "moderator": str(ctx.author.id), "timestamp": str(datetime.datetime.utcnow())})
    save_json(WARNINGS_FILE, warnings)
    await ctx.send(f"⚠️ {member.mention} warned. Reason: {reason} (Total: {len(warnings[gid][uid])})")
    await send_modlog(ctx.guild, "Warn", ctx.author, member, reason, "N/A")

@bot.command()
async def warnings(ctx, member: discord.Member = None):
    member = member or ctx.author
    warns  = load_json(WARNINGS_FILE).get(str(ctx.guild.id), {}).get(str(member.id), [])
    if not warns:
        await ctx.send(f"✅ {member.mention} has no warnings.")
        return
    embed = discord.Embed(title=f"Warnings for {member.name}", color=discord.Color.orange())
    for i, w in enumerate(warns, 1):
        embed.add_field(name=f"Warning {i}", value=f"**Reason:** {w['reason']}\n**When:** {w['timestamp'][:10]}", inline=False)
    await ctx.send(embed=embed)

@bot.command()
@has_mod_role()
async def clearwarnings(ctx, member: discord.Member):
    warnings = load_json(WARNINGS_FILE)
    gid, uid = str(ctx.guild.id), str(member.id)
    if gid in warnings and uid in warnings[gid]:
        warnings[gid][uid] = []
        save_json(WARNINGS_FILE, warnings)
    await ctx.send(f"✅ Warnings cleared for {member.mention}.")

@bot.command()
@has_mod_role()
async def role(ctx, member: discord.Member, *, role_name: str):
    role_obj = discord.utils.get(ctx.guild.roles, name=role_name)
    if not role_obj:
        await ctx.send(f"❌ Role **{role_name}** not found.")
        return
    if role_obj in member.roles:
        await member.remove_roles(role_obj)
        await ctx.send(f"➖ Removed **{role_name}** from {member.mention}.")
    else:
        await member.add_roles(role_obj)
        await ctx.send(f"➕ Added **{role_name}** to {member.mention}.")

@bot.command()
@has_mod_role()
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):
    await member.kick(reason=reason)
    await ctx.send(f"👢 {member.mention} was kicked. Reason: {reason}")
    await send_modlog(ctx.guild, "Kick", ctx.author, member, reason, "N/A")

@bot.command()
@has_mod_role()
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    await member.ban(reason=reason)
    await ctx.send(f"🔨 {member.mention} was banned. Reason: {reason}")
    await send_modlog(ctx.guild, "Ban", ctx.author, member, reason, "Permanent")

@bot.command()
async def timeout(ctx, member: discord.Member, duration: str, *, reason="No reason provided"):
    can_use = any(role.name in MOD_ROLES for role in ctx.author.roles) or \
              any(role.name in TIMEOUT_ROLES for role in ctx.author.roles)
    if not can_use:
        await ctx.send("❌ You don't have permission to use this command.")
        return
    units = {"m": 1, "h": 60, "y": 525600}
    unit  = duration[-1].lower()
    if unit not in units:
        await ctx.send("❌ Use format like `1m`, `2h`, or `1y`")
        return
    try:
        amount = int(duration[:-1])
    except ValueError:
        await ctx.send("❌ Use format like `1m`, `2h`, or `1y`")
        return
    minutes = amount * units[unit]
    await member.timeout(datetime.timedelta(minutes=minutes), reason=reason)
    await ctx.send(f"⏱️ {member.mention} timed out for **{duration}**. Reason: {reason}")
    await send_modlog(ctx.guild, "Timeout", ctx.author, member, reason, duration)

@bot.command()
async def removetimeout(ctx, member: discord.Member):
    can_use = any(role.name in MOD_ROLES for role in ctx.author.roles) or \
              any(role.name in TIMEOUT_ROLES for role in ctx.author.roles)
    if not can_use:
        await ctx.send("❌ You don't have permission to use this command.")
        return
    await member.timeout(None)
    await ctx.send(f"✅ Timeout removed for {member.mention}.")
    await send_modlog(ctx.guild, "Timeout Removed", ctx.author, member, "N/A", "N/A")

# ============================================================
#  MODLOGS COMMAND
# ============================================================
@bot.command()
async def modlogs(ctx, member: discord.Member = None):
    member  = member or ctx.author
    logs    = load_json(MODLOG_FILE)
    entries = logs.get(str(ctx.guild.id), {}).get(str(member.id), [])
    if not entries:
        await ctx.send(f"✅ No mod actions found for {member.mention}.")
        return
    embed = discord.Embed(title=f"📋 Mod Logs — {member.name}", color=discord.Color.blurple(), timestamp=datetime.datetime.utcnow())
    for i, e in enumerate(entries[-10:], 1):
        embed.add_field(
            name  = f"{i}. {e['action']} — {e['timestamp'][:10]}",
            value = f"**By:** {e['moderator']} | **Reason:** {e['reason']} | **Duration:** {e['duration']}",
            inline= False
        )
    embed.set_footer(text=f"Showing last {min(len(entries), 10)} of {len(entries)} entries")
    await ctx.send(embed=embed)

# ============================================================
#  ERROR HANDLING
# ============================================================
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("❌ You don't have permission to use this command.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ Couldn't find that member.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument: `{error.param.name}`")
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        raise error

bot.run(TOKEN)
