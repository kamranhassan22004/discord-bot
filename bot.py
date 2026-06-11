import discord
from discord.ext import commands
import os
import datetime
import json
import asyncio
import yt_dlp
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()

# ============================================================
#  CONFIG — edit these to match your friend's server
# ============================================================
TOKEN                = os.getenv("DISCORD_TOKEN")
WELCOME_CHANNEL_NAME = "welcome"
LEAVE_CHANNEL_NAME   = "welcome"
BOOST_CHANNEL_NAME   = "welcome"
MOD_ROLES            = ["Admin", "Moderator"]
MUTED_ROLE_NAME      = "Muted"

# ============================================================
#  AUTO RESPONSES (built-in defaults)
# ============================================================
AUTO_RESPONSES = {
}

# ============================================================
#  DATA FILES
# ============================================================
WARNINGS_FILE   = "warnings.json"
MSG_COUNT_FILE  = "message_counts.json"
INVITES_FILE    = "invites.json"
AR_FILE         = "auto_responses.json"   # dynamic AR saved here

def load_json(filename):
    if os.path.exists(filename):
        with open(filename, "r") as f:
            return json.load(f)
    return {}

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)

# ============================================================
#  INTENTS
# ============================================================
intents = discord.Intents.default()
intents.members         = True
intents.message_content = True
intents.invites         = True

bot = commands.Bot(command_prefix="!", intents=intents)

invite_cache = {}

# Music queue per guild: {guild_id: [{"url":..., "title":...}]}
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
#  WELCOME MESSAGE + INVITE TRACKING
# ============================================================
@bot.event
async def on_member_join(member):
    guild = member.guild
    used_invite_code = None
    inviter = None
    try:
        new_invites = await guild.fetch_invites()
        old_cache   = invite_cache.get(guild.id, {})
        for inv in new_invites:
            if old_cache.get(inv.code, 0) < inv.uses:
                used_invite_code = inv.code
                inviter = inv.inviter
                break
        invite_cache[guild.id] = {inv.code: inv.uses for inv in new_invites}
        if inviter:
            invite_data = load_json(INVITES_FILE)
            gid = str(guild.id)
            uid = str(inviter.id)
            if gid not in invite_data:
                invite_data[gid] = {}
            invite_data[gid][uid] = invite_data[gid].get(uid, 0) + 1
            save_json(INVITES_FILE, invite_data)
    except Exception:
        pass

    channel = discord.utils.get(guild.text_channels, name=WELCOME_CHANNEL_NAME)
    if channel:
        invite_line = f"\nInvited by **{inviter.name}**" if inviter else ""
        acct_age    = (datetime.datetime.utcnow() - member.created_at.replace(tzinfo=None)).days
        embed = discord.Embed(
            title       = f"Welcome to {guild.name}! 🎉",
            description = (
                f"Hey {member.mention}, glad you're here!\n"
                f"You're member **#{guild.member_count}**{invite_line}\n"
                f"Account created **{acct_age}** days ago."
            ),
            color     = discord.Color.green(),
            timestamp = datetime.datetime.utcnow()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await channel.send(embed=embed)

# ============================================================
#  LEAVE MESSAGE
# ============================================================
@bot.event
async def on_member_remove(member):
    channel = discord.utils.get(member.guild.text_channels, name=LEAVE_CHANNEL_NAME)
    if channel:
        await channel.send(
            f"👋 **{member.name}** has left the server. "
            f"We now have **{member.guild.member_count}** members."
        )

# ============================================================
#  BOOST MESSAGE
# ============================================================
@bot.event
async def on_member_update(before, after):
    if before.premium_since is None and after.premium_since is not None:
        channel = discord.utils.get(after.guild.text_channels, name=BOOST_CHANNEL_NAME)
        if channel:
            embed = discord.Embed(
                title       = "💜 New Server Booster!",
                description = f"Thank you **{after.mention}** for boosting the server! 🚀",
                color       = discord.Color.purple(),
                timestamp   = datetime.datetime.utcnow()
            )
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

    # Count message
    data = load_json(MSG_COUNT_FILE)
    gid  = str(message.guild.id) if message.guild else None
    uid  = str(message.author.id)
    if gid:
        if gid not in data:
            data[gid] = {}
        data[gid][uid] = data[gid].get(uid, 0) + 1
        save_json(MSG_COUNT_FILE, data)

    # Auto response — check dynamic AR first, then built-in defaults
    if message.guild:
        content_lower = message.content.lower()

        # Dynamic AR (saved per guild)
        ar_data = load_json(AR_FILE)
        gid_str = str(message.guild.id)
        guild_ar = ar_data.get(gid_str, {})
        responded = False
        for trigger, response in guild_ar.items():
            if trigger in content_lower:
                await message.channel.send(response)
                responded = True
                break

        # Built-in defaults (only if no dynamic AR matched)
        if not responded:
            for trigger, response in AUTO_RESPONSES.items():
                if trigger in content_lower:
                    await message.channel.send(response)
                    break

    await bot.process_commands(message)

# ============================================================
#  DYNAMIC AUTO RESPONDER COMMANDS
#  !ar add <trigger> <response>
#  !ar remove <trigger>
#  !ar list
# ============================================================
@bot.group(invoke_without_command=True)
async def ar(ctx):
    await ctx.send("Usage: `!ar add <trigger> <response>` | `!ar remove <trigger>` | `!ar list`")

@ar.command(name="add")
@has_mod_role()
async def ar_add(ctx, trigger: str, *, response: str):
    ar_data = load_json(AR_FILE)
    gid     = str(ctx.guild.id)
    if gid not in ar_data:
        ar_data[gid] = {}
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
        removed_response = ar_data[gid].pop(trigger)
        save_json(AR_FILE, ar_data)
        await ctx.send(f"✅ {removed_response}\nTrigger removed.")
    else:
        await ctx.send(f"❌ Trigger `{trigger}` not found.")

@ar.command(name="list")
async def ar_list(ctx):
    ar_data  = load_json(AR_FILE)
    gid      = str(ctx.guild.id)
    guild_ar = ar_data.get(gid, {})
    if not guild_ar:
        await ctx.send("No custom auto-responses set yet. Use `!ar add <trigger> <response>`")
        return
    embed = discord.Embed(title="📋 Auto Responses", color=discord.Color.blurple())
    for trigger, response in guild_ar.items():
        embed.add_field(name=f"`{trigger}`", value=response, inline=False)
    await ctx.send(embed=embed)

# ============================================================
#  MUSIC COMMANDS
#  !play <youtube link or song name>
#  !skip
#  !stop
#  !queue
#  !nowplaying
# ============================================================

YDL_OPTIONS = {
    "format"         : "bestaudio/best",
    "noplaylist"     : True,
    "quiet"          : True,
    "default_search" : "ytsearch",
    "source_address" : "0.0.0.0",
    "extractor_args" : {"youtube": {"skip": ["dash", "hls"]}},
    "http_headers"   : {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    },
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options"       : "-vn",
}

async def play_next(ctx):
    gid = ctx.guild.id
    if music_queues.get(gid):
        next_song = music_queues[gid].pop(0)
        source = await discord.FFmpegOpusAudio.from_probe(next_song["url"], **FFMPEG_OPTIONS)
        ctx.voice_client.play(
            source,
            after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)
        )
        await ctx.send(f"🎵 Now playing: **{next_song['title']}**")
    else:
        await ctx.send("✅ Queue finished.")

@bot.command()
async def play(ctx, *, query: str):
    # Must be in a voice channel
    if not ctx.author.voice:
        await ctx.send("❌ You need to be in a voice channel first!")
        return

    vc = ctx.voice_client
    if not vc:
        vc = await ctx.author.voice.channel.connect()
    elif vc.channel != ctx.author.voice.channel:
        await vc.move_to(ctx.author.voice.channel)

    await ctx.send(f"🔍 Searching for: **{query}**...")

    loop = asyncio.get_event_loop()
    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        try:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(query, download=False))
            if "entries" in info:
                info = info["entries"][0]
            url   = info["url"]
            title = info.get("title", "Unknown")
        except Exception as e:
            await ctx.send(f"❌ Could not find/play that. Try a different query.\n`{e}`")
            return

    gid = ctx.guild.id
    if gid not in music_queues:
        music_queues[gid] = []

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
    gid = ctx.guild.id
    music_queues[gid] = []
    vc = ctx.voice_client
    if vc:
        await vc.disconnect()
        await ctx.send("⏹️ Stopped and left the voice channel.")
    else:
        await ctx.send("❌ Not in a voice channel.")

@bot.command()
async def queue(ctx):
    gid = ctx.guild.id
    q   = music_queues.get(gid, [])
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
        gid = ctx.guild.id
        # The currently playing song was already popped from queue, so just confirm
        await ctx.send("🎵 A song is currently playing. Use `!queue` to see what's next.")
    else:
        await ctx.send("❌ Nothing is playing right now.")

# ============================================================
#  MEMBER COUNT
# ============================================================
@bot.command()
async def membercount(ctx):
    await ctx.send(f"👥 Total members: **{ctx.guild.member_count}**")

# ============================================================
#  MEMBER INFO
# ============================================================
@bot.command()
async def memberinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    roles  = [r.mention for r in member.roles if r.name != "@everyone"]
    embed  = discord.Embed(
        title     = f"Member Info — {member.name}",
        color     = member.color,
        timestamp = datetime.datetime.utcnow()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="ID",              value=member.id,                             inline=True)
    embed.add_field(name="Nickname",        value=member.nick or "None",                 inline=True)
    embed.add_field(name="Joined Server",   value=member.joined_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name="Account Created", value=member.created_at.strftime("%Y-%m-%d"),inline=True)
    embed.add_field(name="Roles",           value=" ".join(roles) if roles else "None",  inline=False)
    warnings   = load_json(WARNINGS_FILE)
    warn_count = len(warnings.get(str(ctx.guild.id), {}).get(str(member.id), []))
    embed.add_field(name="Warnings", value=str(warn_count), inline=True)
    await ctx.send(embed=embed)

# ============================================================
#  SERVER INFO
# ============================================================
@bot.command()
async def serverinfo(ctx):
    guild = ctx.guild
    embed = discord.Embed(title=guild.name, color=discord.Color.blurple(), timestamp=datetime.datetime.utcnow())
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="Owner",   value=guild.owner.mention,                  inline=True)
    embed.add_field(name="Members", value=guild.member_count,                   inline=True)
    embed.add_field(name="Channels",value=len(guild.channels),                  inline=True)
    embed.add_field(name="Roles",   value=len(guild.roles),                     inline=True)
    embed.add_field(name="Boosts",  value=guild.premium_subscription_count,     inline=True)
    embed.add_field(name="Created", value=guild.created_at.strftime("%Y-%m-%d"),inline=True)
    await ctx.send(embed=embed)

# ============================================================
#  MUTE / UNMUTE
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

@bot.command()
@has_mod_role()
async def unmute(ctx, member: discord.Member):
    muted_role = discord.utils.get(ctx.guild.roles, name=MUTED_ROLE_NAME)
    if not muted_role:
        await ctx.send(f"❌ No role named **{MUTED_ROLE_NAME}** found.")
        return
    await member.remove_roles(muted_role)
    await ctx.send(f"🔊 {member.mention} has been unmuted.")

# ============================================================
#  WARN / WARNINGS
# ============================================================
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

@bot.command()
async def warnings(ctx, member: discord.Member = None):
    member   = member or ctx.author
    warnings = load_json(WARNINGS_FILE)
    warns    = warnings.get(str(ctx.guild.id), {}).get(str(member.id), [])
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

# ============================================================
#  ROLE
# ============================================================
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

# ============================================================
#  INVITE COUNTS
# ============================================================
@bot.command()
async def invites(ctx, member: discord.Member = None):
    member      = member or ctx.author
    invite_data = load_json(INVITES_FILE)
    count       = invite_data.get(str(ctx.guild.id), {}).get(str(member.id), 0)
    await ctx.send(f"📨 **{member.name}** has invited **{count}** member(s).")

# ============================================================
#  ACCOUNT AGE
# ============================================================
@bot.command()
async def accountage(ctx, member: discord.Member = None):
    member  = member or ctx.author
    created = member.created_at.replace(tzinfo=None)
    age     = (datetime.datetime.utcnow() - created).days
    await ctx.send(
        f"🗓️ **{member.name}**'s account was created on "
        f"**{member.created_at.strftime('%B %d, %Y')}** "
        f"({age // 365}y {(age % 365) // 30}m {age % 30}d ago)."
    )

# ============================================================
#  LEADERBOARD
# ============================================================
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
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):
    await member.kick(reason=reason)
    await ctx.send(f"👢 {member.mention} was kicked. Reason: {reason}")

@bot.command()
@has_mod_role()
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    await member.ban(reason=reason)
    await ctx.send(f"🔨 {member.mention} was banned. Reason: {reason}")

@bot.command()
@has_mod_role()
async def timeout(ctx, member: discord.Member, duration: str, *, reason="No reason provided"):
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
    minutes  = amount * units[unit]
    delta    = datetime.timedelta(minutes=minutes)
    await member.timeout(delta, reason=reason)
    await ctx.send(f"⏱️ {member.mention} timed out for **{duration}**. Reason: {reason}")

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