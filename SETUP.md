# Discord Mod Bot - Setup Guide

## 1. Configure before running
Open `bot.py` and change:
- `WELCOME_CHANNEL_NAME` → name of your welcome channel (e.g. "welcome")
- `MOD_ROLES` → list of role names allowed to kick/ban/timeout (e.g. ["Admin", "Moderator"])

## 2. Get your bot token
- Go to https://discord.com/developers/applications
- New Application → Bot tab → Reset Token → copy it
- Enable "Server Members Intent" and "Message Content Intent" (under Bot tab)

## 3. Invite bot to server
- OAuth2 → URL Generator
- Scopes: bot, applications.commands
- Permissions: Kick Members, Ban Members, Moderate Members, Send Messages, Read Message History
- Open generated URL → select server → Authorize (server owner must do this if not your server)

## 4. Run locally (for testing)
```
pip install -U discord.py
set DISCORD_TOKEN=your_token_here      (Windows)
export DISCORD_TOKEN=your_token_here   (Mac/Linux)
python bot.py
```

## 5. Deploy 24/7 on Railway (free tier)
1. Create a GitHub repo, push these 3 files (bot.py, requirements.txt, Procfile)
2. Go to railway.app → New Project → Deploy from GitHub repo
3. Select your repo
4. Go to Variables tab → add `DISCORD_TOKEN` = your bot token
5. Railway will auto-detect Procfile and run the bot
6. Bot will show "online" in Discord 24/7

## Commands
- `!membercount` - shows total server members
- `!kick @user [reason]` - kicks member (mod role only)
- `!ban @user [reason]` - bans member (mod role only)
- `!timeout @user <minutes> [reason]` - times out member (mod role only)
- Welcome message auto-posts when someone joins

## IMPORTANT
- Never share your bot token publicly or commit it to GitHub directly - always use environment variables
- If welcome messages don't work, double check "Server Members Intent" is enabled in Developer Portal
