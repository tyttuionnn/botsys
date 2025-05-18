import discord
import datetime
from discord.ext import commands
import asyncio
import os
from discord import app_commands
import yt_dlp as ytdl
from datetime import timedelta
from functools import wraps

def admin_only():
    def decorator(func):
        @wraps(func)
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("Only administrators can use this command.", ephemeral=True)
                return
            return await func(interaction, *args, **kwargs)
        return wrapper
    return decorator

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.voice_states = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Track whether disconnection was manual
manual_disconnects = {}

@bot.event
async def on_voice_state_update(member, before, after):
    # Only run this for the bot's own voice state
    if member.id != bot.user.id:
        return

    # Bot was in a voice channel and got disconnected
    if before.channel and not after.channel:
        guild_id = member.guild.id

        if not manual_disconnects.get(guild_id, False):
            try:
                await before.channel.connect(reconnect=True)
                print(f"Reconnected to {before.channel.name} in {member.guild.name}")
            except Exception as e:
                print(f"Failed to reconnect: {e}")
        else:
            # Reset manual disconnect flag after a clean leave
            manual_disconnects[guild_id] = False

# Check if the bot was disconnected from a voice channel (not just moved)
    if before.channel and after.channel is None:
        # Look at the audit logs to find who disconnected the bot
        async for entry in member.guild.audit_logs(limit=1, action=discord.AuditLogAction.member_disconnect):
            if entry.target.id == bot.user.id and entry.user.guild_permissions.administrator:
                try:
                    await entry.user.send("🚫 Don't use your role to disconnect me. Just use /leave and I will disconnect myself ☺️")
                except discord.Forbidden:
                    print(f"Could not DM {entry.user} (probably has DMs off)")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(e)

# FFmpeg and yt-dlp options
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'  # Disable video since we just want audio
}

# Moderation Commands
@bot.tree.command(name="kick")
@admin_only()
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = None):

    try:
        await member.kick(reason=reason)
        await interaction.response.send_message(f"{member} has been kicked. Reason: {reason}")
    except Exception as e:
        print(e)

@bot.tree.command(name="ban")
@admin_only()
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    try:
        await member.ban(reason=reason)
        await interaction.response.send_message(f"{member} has been banned. Reason: {reason}")
    except Exception as e:
        print(e)

@bot.tree.command(name="unban")
@admin_only()
async def unban(interaction: discord.Interaction, user_id: int):
    try:
        user = await bot.fetch_user(user_id)
        await interaction.guild.unban(user)
        await interaction.response.send_message(f"{user} has been unbanned.")
    except Exception as e:
        print(e)

@bot.tree.command(name="timeout", description="Timeout a member in a voice or text channel")
@admin_only()
@app_commands.describe(member="The user to timeout", duration="The duration of the timeout (in minutes)")
async def timeout(interaction: discord.Interaction, member: discord.Member, duration: int):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    if member == interaction.user:
        await interaction.response.send_message("You cannot timeout yourself.", ephemeral=True)
        return

    try:
        # Timeout for a duration (given in seconds)
        timeout_duration = timedelta(minutes=duration)

        # Apply timeout
        await member.timeout(timeout_duration, reason=f"Timed out by {interaction.user.name} for {duration} minutes.")
        await interaction.response.send_message(f"{member.mention} has been timed out for {duration} minutes.")

    except Exception as e:
        print(f"Error: {e}")
        await interaction.response.send_message("There was an error applying the timeout.", ephemeral=True)

@bot.tree.command(name="remove_timeout")
@admin_only()
async def remove_timeout(interaction: discord.Interaction, member: discord.Member):
    try:
        await member.timeout(None)
        await interaction.response.send_message(f"Timeout removed from {member}.")
    except Exception as e:
        print(e)

@bot.tree.command(name="chat_mute")
@admin_only()
async def chat_mute(interaction: discord.Interaction, member: discord.Member):
    try:
        overwrite = discord.PermissionOverwrite(send_messages=False)
        for channel in interaction.guild.text_channels:
            await channel.set_permissions(member, overwrite=overwrite)
        await interaction.response.send_message(f"{member} has been chat muted.")
    except Exception as e:
        print(e)

@bot.tree.command(name="chat_unmute")
@admin_only()
async def chat_unmute(interaction: discord.Interaction, member: discord.Member):
    try:
        for channel in interaction.guild.text_channels:
            await channel.set_permissions(member, overwrite=None)
        await interaction.response.send_message(f"{member} has been chat unmuted.")
    except Exception as e:
        print(e)

@bot.tree.command(name="voice_mute")
@admin_only()
async def voice_mute(interaction: discord.Interaction, member: discord.Member):
    try:
        await member.edit(mute=True)
        await interaction.response.send_message(f"{member} has been voice muted.")
    except Exception as e:
        print(e)

@bot.tree.command(name="voice_unmute")
@admin_only()
async def voice_unmute(interaction: discord.Interaction, member: discord.Member):
    try:
        await member.edit(mute=False)
        await interaction.response.send_message(f"{member} has been voice unmuted.")
    except Exception as e:
        print(e)

# Info Commands
@bot.tree.command(name="userinfo")
async def userinfo(interaction: discord.Interaction, member: discord.Member):
    try:
        embed = discord.Embed(title=f"User Info - {member}", color=discord.Color.blue())
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
        embed.add_field(name="Username", value=member.name, inline=True)
        embed.add_field(name="Discriminator", value=member.discriminator, inline=True)
        embed.add_field(name="User ID", value=member.id, inline=True)
        embed.add_field(name="Nickname", value=member.nick or "None", inline=True)
        embed.add_field(name="Top Role", value=member.top_role.mention, inline=True)
        embed.add_field(name="Bot?", value=member.bot, inline=True)
        embed.add_field(name="Status", value=member.status, inline=True)
        embed.add_field(name="Joined Server", value=member.joined_at.strftime("%Y-%m-%d %H:%M:%S"), inline=True)
        embed.add_field(name="Account Created", value=member.created_at.strftime("%Y-%m-%d %H:%M:%S"), inline=True)
        roles = ", ".join([role.mention for role in member.roles if role.name != "@everyone"])
        embed.add_field(name="Roles", value=roles if roles else "None", inline=False)

        await interaction.response.send_message(embed=embed)
    except Exception as e:
        print(e)

@bot.tree.command(name="serverinfo")
async def serverinfo(interaction: discord.Interaction):
    try:
        guild = interaction.guild
        embed = discord.Embed(title=f"Server Info - {guild.name}", color=discord.Color.green())
        embed.set_thumbnail(url=guild.icon.url if guild.icon else discord.Embed.Empty)
        embed.add_field(name="Server ID", value=guild.id, inline=True)
        embed.add_field(name="Owner", value=guild.owner.mention, inline=True)
        embed.add_field(name="Region", value=guild.preferred_locale, inline=True)
        embed.add_field(name="Members", value=guild.member_count, inline=True)
        embed.add_field(name="Roles", value=len(guild.roles), inline=True)
        embed.add_field(name="Text Channels", value=len(guild.text_channels), inline=True)
        embed.add_field(name="Voice Channels", value=len(guild.voice_channels), inline=True)
        embed.add_field(name="Categories", value=len(guild.categories), inline=True)
        embed.add_field(name="Created On", value=guild.created_at.strftime("%Y-%m-%d %H:%M:%S"), inline=True)

        await interaction.response.send_message(embed=embed)
    except Exception as e:
        print(e)

# Poll Command
@bot.tree.command(name="poll", description="Create a custom poll with multiple options. Use semicolons to separate options.")
async def poll(interaction: discord.Interaction, question: str, options: str):
    try:
        # Split and clean options
        option_list = [opt.strip() for opt in options.split(";") if opt.strip()]
        
        if len(option_list) < 2:
            await interaction.response.send_message("You must provide at least 2 options.", ephemeral=True)
            return
        if len(option_list) > 10:
            await interaction.response.send_message("You can only provide up to 10 options.", ephemeral=True)
            return

        emoji_numbers = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        description = ""
        for i, opt in enumerate(option_list):
            description += f"{emoji_numbers[i]} {opt}\n"

        embed = discord.Embed(title=f"📊 {question}", description=description, color=discord.Color.purple())
        poll_message = await interaction.channel.send(embed=embed)

        for i in range(len(option_list)):
            await poll_message.add_reaction(emoji_numbers[i])

        await interaction.response.send_message("Poll created!", ephemeral=True)
    except Exception as e:
        print(e)

# Voice Channel Commands
@bot.tree.command(name="join")
async def join(interaction: discord.Interaction, channel: discord.VoiceChannel):
    try:
        manual_disconnects[interaction.guild.id] = False  # Reset manual flag
        await channel.connect()
        await interaction.response.send_message(f"Joined {channel.name}")
    except Exception as e:
        print(e)

@bot.tree.command(name="leave")
async def leave(interaction: discord.Interaction):
    try:
        if interaction.guild.voice_client:
            manual_disconnects[interaction.guild.id] = True
            await interaction.guild.voice_client.disconnect()
            await interaction.response.send_message("Disconnected from voice channel.")
        else:
            await interaction.response.send_message("I'm not connected to a voice channel.", ephemeral=True)
    except Exception as e:
        print(e)

# Play Local MP3 File
@bot.tree.command(name="playlocal")
async def playlocal(interaction: discord.Interaction, filename: str):
    try:
        voice_client = interaction.guild.voice_client
        if not voice_client:
            await interaction.response.send_message("Bot is not connected to a voice channel.", ephemeral=True)
            return

        file_path = os.path.join(os.getcwd(), filename)
        if not os.path.isfile(file_path):
            await interaction.response.send_message("File not found in bot directory.", ephemeral=True)
            return

        if voice_client.is_playing():
            voice_client.stop()

        voice_client.play(discord.FFmpegPCMAudio(file_path))
        await interaction.response.send_message(f"Now playing: {filename}")
    except Exception as e:
        print(e)

# Download and extract audio from YouTube link using yt-dlp
def get_audio_stream(url):
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'extractaudio': True,
            'audioquality': 1,
            'outtmpl': 'downloads/%(id)s.%(ext)s',
        }

        with ytdl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            audio_url = info['formats'][0]['url']  # Get the best audio URL
            print(f"Audio URL: {audio_url}")
            return audio_url
    except Exception as e:
        print(f"Error fetching audio stream: {e}")
        return None

# Download and extract audio from YouTube link using yt-dlp (without saving it)
def get_audio_stream(url):
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'extractaudio': True,
            'audioquality': 1,
            'outtmpl': 'downloads/%(id)s.%(ext)s',
        }

        with ytdl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            audio_url = info['formats'][0]['url']  # Get the best audio URL
            print(f"Audio URL: {audio_url}")
            return audio_url
    except Exception as e:
        print(f"Error fetching audio stream: {e}")
        return None

# Command to play music from a YouTube URL
@bot.tree.command(name="muzika")
@app_commands.describe(url="The URL of the music to play (e.g. YouTube link)")
async def muzika(interaction: discord.Interaction, url: str):
    try:
        # Ensure the user is in a voice channel
        voice_channel = interaction.user.voice.channel
        if not voice_channel:
            await interaction.response.send_message("You need to join a voice channel first.", ephemeral=True)
            return
        
        # Connect to the voice channel
        print(f"Connecting to voice channel: {voice_channel.name}")
        voice_client = await voice_channel.connect()

        # If the URL is from YouTube, use yt-dlp to get the stream
        audio_url = get_audio_stream(url)

        if not audio_url:
            await interaction.response.send_message("Error fetching the audio from the provided link.", ephemeral=True)
            return

        # Play the audio directly from the URL
        voice_client.play(discord.FFmpegPCMAudio(audio_url, **FFMPEG_OPTIONS))

        # Send message that music is playing
        await interaction.response.send_message(f"Now playing: {url}")

        # Wait until the audio finishes playing
        while voice_client.is_playing():
            await asyncio.sleep(1)

        # Disconnect from the voice channel when done
        await voice_client.disconnect()

    except Exception as e:
        print(f"Error in muzika command: {e}")
        await interaction.response.send_message("There was an error playing the music.", ephemeral=True)

# Command to skip music
@bot.tree.command(name="skip")
async def skip(interaction: discord.Interaction):
    try:
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.stop()
            await interaction.response.send_message("Music has been skipped.")
        else:
            await interaction.response.send_message("No music is currently playing.", ephemeral=True)
    except Exception as e:
        print(f"Error in skip command: {e}")
        await interaction.response.send_message("There was an error skipping the music.", ephemeral=True)

# Command to pause music
@bot.tree.command(name="pause")
async def pause(interaction: discord.Interaction):
    try:
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.pause()
            await interaction.response.send_message("Music has been paused.")
        else:
            await interaction.response.send_message("No music is currently playing.", ephemeral=True)
    except Exception as e:
        print(f"Error in pause command: {e}")
        await interaction.response.send_message("There was an error pausing the music.", ephemeral=True)
        
# Ping Command
@bot.tree.command(name="ping")
async def ping(interaction: discord.Interaction):
    try:
        await interaction.response.send_message(f"🏓 Pong! Latency: {round(bot.latency * 1000)}ms")
    except Exception as e:
        print(e)

# Run the bot
bot.run("")
#FINISHED
