import discord
from discord.ext import commands
import os

# ---------- CONFIG ----------
TOKEN = os.getenv("DISCORD_TOKEN")  # set this in Railway/host env variables, never hardcode
WELCOME_CHANNEL_NAME = "welcome"     # change to your server's welcome channel name
MOD_ROLES = ["Admin", "Moderator"]   # change to your actual role names

# ---------- INTENTS ----------
intents = discord.Intents.default()
intents.members = True          # required for join events + member count
intents.message_content = True  # required for prefix commands

bot = commands.Bot(command_prefix="!", intents=intents)


# ---------- READY ----------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")


# ---------- WELCOME MESSAGE ----------
@bot.event
async def on_member_join(member):
    channel = discord.utils.get(member.guild.text_channels, name=WELCOME_CHANNEL_NAME)
    if channel:
        await channel.send(
            f"Welcome {member.mention} to **{member.guild.name}**! "
            f"You're member #{member.guild.member_count}."
        )


# ---------- MEMBER COUNT COMMAND ----------
@bot.command()
async def membercount(ctx):
    await ctx.send(f"Total members: **{ctx.guild.member_count}**")


# ---------- PERMISSION CHECK ----------
def has_mod_role():
    async def predicate(ctx):
        return any(role.name in MOD_ROLES for role in ctx.author.roles)
    return commands.check(predicate)


# ---------- KICK ----------
@bot.command()
@has_mod_role()
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):
    await member.kick(reason=reason)
    await ctx.send(f"👢 {member.mention} was kicked. Reason: {reason}")


# ---------- BAN ----------
@bot.command()
@has_mod_role()
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    await member.ban(reason=reason)
    await ctx.send(f"🔨 {member.mention} was banned. Reason: {reason}")


# ---------- TIMEOUT ----------
# duration in minutes
@bot.command()
@has_mod_role()
async def timeout(ctx, member: discord.Member, minutes: int, *, reason="No reason provided"):
    import datetime
    duration = datetime.timedelta(minutes=minutes)
    await member.timeout(duration, reason=reason)
    await ctx.send(f"⏱️ {member.mention} was timed out for {minutes} minute(s). Reason: {reason}")


# ---------- ERROR HANDLING ----------
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("❌ You don't have permission to use this command.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ Couldn't find that member.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument: {error.param.name}")
    else:
        raise error


bot.run(TOKEN)
