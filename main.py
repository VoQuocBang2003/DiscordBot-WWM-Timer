import discord
from discord.ext import commands, tasks
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None
import asyncio
import os
import sys
import traceback
import shutil
import json

from dotenv import load_dotenv
from aiohttp import web

load_dotenv()

# Try to ensure opus library is available for voice features.
try:
    import discord.opus as _opus
except Exception:
    _opus = None

def try_load_opus():
    if not _opus:
        print("discord.opus module not available; voice may not work")
        return False
    if _opus.is_loaded():
        return True

    candidates = []
    env_path = os.getenv("OPUS_LIB_PATH")
    if env_path:
        candidates.append(env_path)

    common_names = [
        "libopus-0.x64.dll",
        "libopus-0.x86.dll",
        "libopus-0.dll",
        "libopus.dll",
    ]
    for name in common_names:
        candidates.append(os.path.join(os.getcwd(), name))
        candidates.append(os.path.join(os.getcwd(), "bin", name))
        candidates.append(os.path.join(sys.exec_prefix, "DLLs", name))

    for path in candidates:
        if not path:
            continue
        try:
            if os.path.exists(path):
                try:
                    _opus.load_opus(path)
                except Exception:
                    continue
                if _opus.is_loaded():
                    print(f"Loaded opus from: {path}")
                    return True
        except Exception:
            continue

    print("Opus library not loaded. Voice will not work until you install libopus.")
    print("Recommended: download a Windows build of libopus and set OPUS_LIB_PATH or place the DLL in the project folder.")
    print("Example source: https://github.com/jiixyj/opus-windows-builds/releases or build from https://opus-codec.org/")
    print("After placing the DLL, you can set OPUS_LIB_PATH environment variable or restart the bot.")
    return False

OPUS_OK = try_load_opus()

# Check for davey backend availability
try:
    import davey
    DAVEY_OK = True
except Exception:
    davey = None
    DAVEY_OK = False

# timezone name can be customized via TIMEZONE env var (default: Asia/Ho_Chi_Minh)
TZ_NAME = os.getenv("TIMEZONE", "Asia/Ho_Chi_Minh")
try:
    if ZoneInfo:
        TZ = ZoneInfo(TZ_NAME)
    else:
        raise Exception()
except Exception:
    try:
        import pytz

        TZ = pytz.timezone(TZ_NAME)
    except Exception:
        TZ = None
        print("Warning: timezone support not available; using system local time")

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    print("Error: DISCORD_TOKEN not set in environment (.env)")
    sys.exit(1)

intents = discord.Intents.all()
# Optional application id for the bot (useful for some discord features)
APP_ID = os.getenv("APPLICATION_ID")
if APP_ID:
    try:
        app_id_val = int(APP_ID)
    except Exception:
        app_id_val = None
else:
    app_id_val = None

if app_id_val:
    bot = commands.Bot(command_prefix="!", intents=intents, application_id=app_id_val)
else:
    bot = commands.Bot(command_prefix="!", intents=intents)


@bot.command()
async def checkopus(ctx):
    """Check and attempt to load Opus library on demand."""
    if not _opus:
        await ctx.send("discord.opus module not available in this Python environment.")
        return
    if _opus.is_loaded():
        await ctx.send("Opus is already loaded.")
        return

    # try loading again from OPUS_LIB_PATH or common names
    env_path = os.getenv("OPUS_LIB_PATH")
    if env_path and os.path.exists(env_path):
        try:
            _opus.load_opus(env_path)
        except Exception as e:
            await ctx.send(f"Failed to load opus from OPUS_LIB_PATH: {e}")
            return
        await ctx.send(f"Loaded opus from OPUS_LIB_PATH: {env_path}")
        return

    # try common filenames in project
    tried = []
    for name in ["libopus-0.x64.dll", "libopus-0.dll", "libopus.dll"]:
        path = os.path.join(os.getcwd(), name)
        tried.append(path)
        if os.path.exists(path):
            try:
                _opus.load_opus(path)
            except Exception as e:
                await ctx.send(f"Tried {path} but failed: {e}")
                return
            await ctx.send(f"Loaded opus from: {path}")
            return

    await ctx.send("Opus not loaded. Try placing the DLL in the project folder or set OPUS_LIB_PATH. Tried: " + ", ".join(tried))


@bot.command()
async def checkvoice(ctx):
    """Report voice-related components: PyNaCl, Opus, ffmpeg."""
    msgs = []
    try:
        import nacl
        msgs.append(f"PyNaCl: {nacl.__version__}")
    except Exception as e:
        msgs.append(f"PyNaCl: NOT INSTALLED ({e})")

    msgs.append(f"davey installed: {DAVEY_OK}")

    msgs.append(f"Opus loaded: {(_opus.is_loaded() if _opus else False)}")

    import shutil
    ff = shutil.which("ffmpeg")
    msgs.append(f"ffmpeg: {ff if ff else 'not found in PATH'}")

    await ctx.send("\n".join(msgs))

# ====== CONFIG ======
VOICE_CHANNEL_ID = None  # sẽ set bằng lệnh
# Optional default voice channel ID from env
if os.getenv("VOICE_CHANNEL_ID"):
    try:
        VOICE_CHANNEL_ID = int(os.getenv("VOICE_CHANNEL_ID"))
    except Exception:
        VOICE_CHANNEL_ID = None

SCHEDULE = [
    {"day": 5, "time": "19:32:00", "sound": "welcome.ogg", "enabled": True},  # Thứ 7
    {"day": 5, "time": "19:34:30", "sound": "30sec.ogg", "enabled": True},
    {"day": 5, "time": "19:39:00", "sound": "1minute.ogg", "enabled": True},
    {"day": 5, "time": "19:44:00", "sound": "1minute.ogg", "enabled": True},
    {"day": 5, "time": "19:49:00", "sound": "1minute.ogg", "enabled": True},
    {"day": 6, "time": "19:32:00", "sound": "welcome.ogg", "enabled": True},  # CN
    {"day": 6, "time": "19:34:30", "sound": "30sec.ogg", "enabled": True},
    {"day": 6, "time": "19:39:00", "sound": "1minute.ogg", "enabled": True},
    {"day": 6, "time": "19:44:00", "sound": "1minute.ogg", "enabled": True},
    {"day": 6, "time": "19:49:00", "sound": "1minute.ogg", "enabled": True}
]

# Persistence for schedule
SCHEDULE_FILE = "schedule.json"

def load_schedules():
    global SCHEDULE
    if os.path.exists(SCHEDULE_FILE):
        try:
            with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    # ensure entries have enabled flag
                    for ev in data:
                        if "enabled" not in ev:
                            ev["enabled"] = True
                    SCHEDULE = data
                    print(f"Loaded schedule from {SCHEDULE_FILE}")
        except Exception as e:
            print(f"Failed to load schedule from {SCHEDULE_FILE}: {e}")

def save_schedules():
    try:
        with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
            json.dump(SCHEDULE, f, ensure_ascii=False, indent=2)
        print(f"Saved schedule to {SCHEDULE_FILE}")
    except Exception as e:
        print(f"Failed to save schedule to {SCHEDULE_FILE}: {e}")

# load persisted schedule if present
load_schedules()

# Built-in default schedule (fixed and not listed/managed via the editable SCHEDULE)
# These run on Saturday (5) and Sunday (6) at configured times.
DEFAULT_SCHEDULE = [
    {"day": 5, "time": "19:32:00", "sound": "welcome.ogg"},
    {"day": 5, "time": "19:34:30", "sound": "30sec.ogg"},
    {"day": 5, "time": "19:39:00", "sound": "1minute.ogg"},
    {"day": 5, "time": "19:44:00", "sound": "1minute.ogg"},
    {"day": 5, "time": "19:49:00", "sound": "1minute.ogg"},
    {"day": 6, "time": "19:32:00", "sound": "welcome.ogg"},
    {"day": 6, "time": "19:34:30", "sound": "30sec.ogg"},
    {"day": 6, "time": "19:39:00", "sound": "1minute.ogg"},
    {"day": 6, "time": "19:44:00", "sound": "1minute.ogg"},
    {"day": 6, "time": "19:49:00", "sound": "1minute.ogg"}
]

# Persistence for default schedule enabled flag
DEFAULT_FLAG_FILE = "default_enabled.json"

def load_default_enabled():
    try:
        if os.path.exists(DEFAULT_FLAG_FILE):
            with open(DEFAULT_FLAG_FILE, "r", encoding="utf-8") as f:
                j = json.load(f)
                return bool(j.get("default_enabled", True))
    except Exception:
        pass
    return True

def save_default_enabled(val: bool):
    try:
        with open(DEFAULT_FLAG_FILE, "w", encoding="utf-8") as f:
            json.dump({"default_enabled": bool(val)}, f)
    except Exception as e:
        print(f"Failed to save default enabled flag: {e}")

# load default enabled state
DEFAULT_ENABLED = load_default_enabled()

# Default channel id for the built-in DEFAULT_SCHEDULE (can be changed here)
DEFAULT_CHANNEL_ID = 1505248166813892810

played_today = set()
TIMER_ENABLED = True

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    print("Opus loaded at startup:", (_opus.is_loaded() if _opus else False))
    # if not loaded yet, try loading once more from OPUS_LIB_PATH or common names
    if _opus and not _opus.is_loaded():
        env_path = os.getenv("OPUS_LIB_PATH")
        if env_path and os.path.exists(env_path):
            try:
                _opus.load_opus(env_path)
                print(f"Loaded opus from OPUS_LIB_PATH at on_ready: {env_path}")
            except Exception as e:
                print("Failed to load opus from OPUS_LIB_PATH at on_ready:", e)
        else:
            for name in ["libopus-0.x64.dll", "libopus-0.dll", "libopus.dll"]:
                path = os.path.join(os.getcwd(), name)
                if os.path.exists(path):
                    try:
                        _opus.load_opus(path)
                        print(f"Loaded opus from: {path}")
                        break
                    except Exception as e:
                        print(f"Failed to load {path} at on_ready:", e)

    check_schedule.start()

@tasks.loop(seconds=1)
async def check_schedule():
    global played_today

    now = datetime.now(TZ) if TZ else datetime.now()
    current_day = now.weekday()
    current_time = now.strftime("%H:%M:%S")
    current_date = now.strftime("%Y-%m-%d")
    current_datetime = now.strftime("%Y-%m-%d %H:%M:%S")

    # reset mỗi ngày
    if current_time == "00:00:00":
        played_today.clear()

    for idx, event in enumerate(SCHEDULE):
        # two kinds of entries: recurring by weekday ('day' + 'time') or one-off by date ('date' + 'time')
        if not event.get("enabled", True):
            continue

        if "date" in event:
            # one-off schedule: date format YYYY-MM-DD and time HH:MM:SS
            ev_date = event.get("date")
            ev_time = event.get("time")
            key = f"date-{ev_date}-{ev_time}"
            if ev_date == current_date and ev_time == current_time and key not in played_today:
                chan_id = event.get("channel_id")
                await play_sound(event["sound"], chan_id)
                played_today.add(key)
                # disable one-off entry after running and persist
                event["enabled"] = False
                save_schedules()

        elif "day" in event:
            ev_day = event.get("day")
            ev_time = event.get("time")
            key = f"{ev_day}-{ev_time}"
            if ev_day == current_day and ev_time == current_time and key not in played_today and event.get("enabled", True):
                chan_id = event.get("channel_id")
                await play_sound(event["sound"], chan_id)
                played_today.add(key)

    # run built-in default schedule independently if enabled
    if DEFAULT_ENABLED:
        for ev in DEFAULT_SCHEDULE:
            ev_day = ev.get("day")
            ev_time = ev.get("time")
            key = f"default-{ev_day}-{ev_time}"
            if ev_day == current_day and ev_time == current_time and key not in played_today:
                # preference: event.channel_id -> DEFAULT_CHANNEL_ID -> VOICE_CHANNEL_ID
                chan_id = ev.get("channel_id") if ev.get("channel_id") else (DEFAULT_CHANNEL_ID or VOICE_CHANNEL_ID)
                await play_sound(ev["sound"], chan_id)
                played_today.add(key)

async def play_sound(filename, channel_or_id=None, force_pcm=False):
    global VOICE_CHANNEL_ID

    # determine target channel
    target_channel = None
    if channel_or_id is None:
        if VOICE_CHANNEL_ID is None:
            return
        target_channel = bot.get_channel(VOICE_CHANNEL_ID)
    else:
        if isinstance(channel_or_id, int):
            target_channel = bot.get_channel(channel_or_id)
        else:
            target_channel = channel_or_id

    if not target_channel:
        return

    # reuse existing voice client if present in the guild
    existing_vc = discord.utils.get(bot.voice_clients, guild=target_channel.guild)
    created_connection = False
    if existing_vc and existing_vc.is_connected():
        vc = existing_vc
    else:
        try:
            vc = await target_channel.connect()
            created_connection = True
        except Exception as e:
            print(f"Failed to connect to voice channel {getattr(target_channel, 'id', None)}: {e}")
            traceback.print_exc()
            return

    path = os.path.join("sounds", filename)

    # find ffmpeg executable: env override `FFMPEG_PATH` or system PATH
    ffmpeg_exe = os.getenv("FFMPEG_PATH") or shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if not ffmpeg_exe:
        print("Warning: ffmpeg not found in PATH and FFMPEG_PATH not set. Audio may fail.")

    # log and verify file
    if not os.path.exists(path):
        print(f"Audio file not found: {path}")
        return
    try:
        size = os.path.getsize(path)
    except Exception:
        size = None
    print(f"Playing file: {path} (size={size}) using ffmpeg: {ffmpeg_exe}")

    # Try Opus-encoded ffmpeg output first (preferred when Opus available), then fallback to PCM re-encode.
    using_opus_audio = False
    ff_src = None
    source = None

    # common ffmpeg before options (don't use -re for local file playback)
    before_opts = "-hide_banner -loglevel warning -nostdin"
    # attempt Opus encoding with ffmpeg (outputs an opus stream directly)
    if not force_pcm and _opus and _opus.is_loaded():
        try:
            opus_opts = "-vn -f opus"
            if ffmpeg_exe:
                ff_src = discord.FFmpegOpusAudio(path, executable=ffmpeg_exe, before_options=before_opts, options=opus_opts)
            else:
                ff_src = discord.FFmpegOpusAudio(path, before_options=before_opts, options=opus_opts)
            source = ff_src
            using_opus_audio = True
            print("Using FFmpegOpusAudio (opus passthrough) for playback")
        except Exception as e:
            print("Opus passthrough failed, will fallback to PCM re-encode:", e)

    if not using_opus_audio:
        try:
            # Explicitly request pcm_s16le codec and canonical sample rate/channels
            options = "-vn -f s16le -acodec pcm_s16le"
            if ffmpeg_exe:
                ff_src = discord.FFmpegPCMAudio(path, executable=ffmpeg_exe, before_options=before_opts, options=options)
            else:
                ff_src = discord.FFmpegPCMAudio(path, before_options=before_opts, options=options)
            try:
                # boost volume for testing
                source = discord.PCMVolumeTransformer(ff_src, volume=5.0)
            except Exception:
                source = ff_src
            print("Using FFmpegPCMAudio (PCM) for playback with volume=5.0")
        except Exception as e:
            print("Failed to create PCM audio source:", e)
            traceback.print_exc()
            return

    # ensure any previous audio is stopped so we do not loop or overlap
    try:
        vc.stop()
    except Exception:
        pass

    # play once (no after callback that would restart playback)
    vc.play(source)
    try:
        # print voice client and guild voice state diagnostics
        try:
            bot_voice_state = target_channel.guild.me.voice
            print(f"Voice client connected: {vc.is_connected()}, is_playing: {vc.is_playing()}, channel={getattr(vc.channel, 'name', None)}")
            if bot_voice_state:
                print(f"Bot voice state - self_mute={bot_voice_state.self_mute}, self_deaf={bot_voice_state.self_deaf}, mute={bot_voice_state.mute}, deaf={bot_voice_state.deaf}")
        except Exception:
            pass

        proc = None
        # check different attributes depending on source type
        if hasattr(source, 'process') and getattr(source, 'process'):
            proc = source.process
        elif hasattr(source, '_process') and getattr(source, '_process'):
            proc = source._process
        elif ff_src is not None and hasattr(ff_src, 'process') and getattr(ff_src, 'process'):
            proc = ff_src.process
        elif ff_src is not None and hasattr(ff_src, '_process') and getattr(ff_src, '_process'):
            proc = ff_src._process
        pid = getattr(proc, 'pid', None) if proc else None
        print(f"Started ffmpeg process pid={pid} (exe={ffmpeg_exe})")
        print(f"Using_opus_audio={using_opus_audio}")
    except Exception:
        pass

    while vc.is_playing():
        await asyncio.sleep(1)

    # log termination
    try:
        rc = None
        proc = None
        if hasattr(source, 'process') and getattr(source, 'process'):
            proc = source.process
        elif hasattr(source, '_process') and getattr(source, '_process'):
            proc = source._process
        elif ff_src is not None and hasattr(ff_src, 'process') and getattr(ff_src, 'process'):
            proc = ff_src.process
        elif ff_src is not None and hasattr(ff_src, '_process') and getattr(ff_src, '_process'):
            proc = ff_src._process
        if proc:
            rc = proc.returncode
        print(f"Playback finished, ffmpeg returncode={rc}")
    except Exception:
        pass

    if created_connection:
        await vc.disconnect()

# ===== COMMAND =====

@bot.command()
async def setvoice(ctx):
    global VOICE_CHANNEL_ID
    if ctx.author.voice:
        VOICE_CHANNEL_ID = ctx.author.voice.channel.id
        await ctx.send("Đã set voice channel!")
    else:
        await ctx.send("Bạn phải vào voice trước!")


@bot.command()
async def listvoices(ctx):
    """Liệt kê các voice channel trong server hiện tại với chỉ số"""
    vcs = [c for c in ctx.guild.channels if isinstance(c, discord.VoiceChannel)]
    if not vcs:
        await ctx.send("Không tìm thấy voice channel nào trong server này.")
        return
    lines = [f"{i+1}. {c.name} (id: {c.id})" for i, c in enumerate(vcs)]
    await ctx.send("\n".join(lines))


@bot.command()
async def listschedule(ctx):
    """List scheduled events with index and status."""
    if not SCHEDULE:
        await ctx.send("Không có lịch nào.")
        return
    lines = []
    for i, ev in enumerate(SCHEDULE, start=1):
        day = ev.get("day")
        time = ev.get("time")
        sound = ev.get("sound")
        enabled = ev.get("enabled", True)
        chan_id = ev.get("channel_id")
        chan_name = None
        if chan_id:
            ch = bot.get_channel(chan_id)
            chan_name = ch.name if ch else str(chan_id)
        lines.append(f"{i}. day={day} time={time} sound={sound} enabled={enabled} channel={chan_name}")
    # send in multiple messages if long
    for chunk_start in range(0, len(lines), 10):
        await ctx.send("\n".join(lines[chunk_start:chunk_start+10]))


@bot.command()
async def delschedule(ctx, index: int):
    """Delete schedule entry by index (1-based)."""
    if index < 1 or index > len(SCHEDULE):
        await ctx.send("Index không hợp lệ.")
        return
    ev = SCHEDULE.pop(index - 1)
    save_schedules()
    await ctx.send(f"Deleted schedule #{index}.")


@bot.command()
async def toggleschedule(ctx, index: int):
    """Toggle enabled/disabled for schedule entry by index (1-based)."""
    if index < 1 or index > len(SCHEDULE):
        await ctx.send("Index không hợp lệ.")
        return
    ev = SCHEDULE[index - 1]
    ev["enabled"] = not ev.get("enabled", True)
    save_schedules()
    await ctx.send(f"Schedule #{index} enabled={ev['enabled']}")
    
@bot.command()
async def defaultschedule(ctx, mode: str = None):
    """Manage the built-in default schedule: `!defaultschedule on|off|status`"""
    global DEFAULT_ENABLED
    if not mode:
        await ctx.send(f"Default schedule enabled={DEFAULT_ENABLED}")
        return
    m = mode.lower()
    if m == "on":
        DEFAULT_ENABLED = True
        save_default_enabled(True)
        await ctx.send("Default schedule enabled.")
    elif m == "off":
        DEFAULT_ENABLED = False
        save_default_enabled(False)
        await ctx.send("Default schedule disabled.")
    elif m == "status":
        await ctx.send(f"Default schedule enabled={DEFAULT_ENABLED}")
    else:
        await ctx.send("Sử dụng: `!defaultschedule on|off|status`")


@bot.command()
async def setschedulechannel(ctx, index: int):
    """Set schedule entry's voice channel to your current voice channel."""
    if index < 1 or index > len(SCHEDULE):
        await ctx.send("Index không hợp lệ.")
        return
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("Bạn phải ở trong voice channel để gán lịch.")
        return
    ch = ctx.author.voice.channel
    ev = SCHEDULE[index - 1]
    ev["channel_id"] = ch.id
    save_schedules()
    await ctx.send(f"Schedule #{index} sẽ phát vào kênh **{ch.name}**")


@bot.command()
async def clearschedulechannel(ctx, index: int):
    """Clear per-event channel override."""
    if index < 1 or index > len(SCHEDULE):
        await ctx.send("Index không hợp lệ.")
        return
    ev = SCHEDULE[index - 1]
    if "channel_id" in ev:
        ev.pop("channel_id")
        save_schedules()
        await ctx.send(f"Schedule #{index} channel cleared.")
    else:
        await ctx.send(f"Schedule #{index} has no channel override.")


@bot.command()
async def addschedule(ctx, day: int, time_str: str, sound: str, channel_index: int = None):
    """Add a schedule entry: `!addschedule <day(0-6)> <HH:MM:SS> <sound> [channel_index]`.
    If channel_index omitted and you're in voice, schedule will use your current voice channel."""
    # validate day
    if day < 0 or day > 6:
        await ctx.send("Day must be 0-6 (Mon=0, Sun=6).")
        return
    # validate time
    try:
        datetime.strptime(time_str, "%H:%M:%S")
    except Exception:
        await ctx.send("Time must be in HH:MM:SS format.")
        return
    if not sound.lower().endswith((".ogg", ".mp3", ".wav")):
        sound = f"{sound}.ogg"

    entry = {"day": day, "time": time_str, "sound": sound, "enabled": True}
    # optional channel index maps to guild voice channels
    if channel_index is not None:
        vcs = [c for c in ctx.guild.channels if isinstance(c, discord.VoiceChannel)]
        if channel_index < 1 or channel_index > len(vcs):
            await ctx.send(f"Channel index invalid. Use `!listvoices` to get indices.")
            return
        entry["channel_id"] = vcs[channel_index - 1].id
    else:
        # if user is in voice, set as default channel for this event
        if ctx.author.voice and ctx.author.voice.channel:
            entry["channel_id"] = ctx.author.voice.channel.id

    SCHEDULE.append(entry)
    save_schedules()
    await ctx.send(f"Added schedule #{len(SCHEDULE)}: day={day} time={time_str} sound={sound}")


@bot.command()
async def createschedule(ctx):
    """Interactive flow to create a schedule safely (choose voice, day/date, time, and sound)."""
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    # 1) choose voice channel option
    vcs = [c for c in ctx.guild.channels if isinstance(c, discord.VoiceChannel)]
    lines = [f"0. Use my current voice channel (if you're in one)"]
    for i, c in enumerate(vcs, start=1):
        lines.append(f"{i}. {c.name} (id: {c.id})")
    await ctx.send("Chọn kênh voice (nhập số):\n" + "\n".join(lines))
    try:
        msg = await bot.wait_for('message', check=check, timeout=60)
        choice = int(msg.content.strip())
    except Exception:
        await ctx.send("Không nhận được phản hồi hợp lệ (timeout hoặc nhập sai). Hủy.")
        return

    chosen_channel_id = None
    if choice == 0:
        if ctx.author.voice and ctx.author.voice.channel:
            chosen_channel_id = ctx.author.voice.channel.id
        else:
            await ctx.send("Bạn không ở trong voice. Hủy.")
            return
    else:
        if choice < 1 or choice > len(vcs):
            await ctx.send("Index kênh không hợp lệ. Hủy.")
            return
        chosen_channel_id = vcs[choice - 1].id

    # 2) recurring or one-off
    await ctx.send("Loại lịch: 1. Recurring (hàng tuần)  2. One-off (theo ngày). Nhập 1 hoặc 2:")
    try:
        msg = await bot.wait_for('message', check=check, timeout=60)
        kind = int(msg.content.strip())
    except Exception:
        await ctx.send("Timeout hoặc đầu vào không hợp lệ. Hủy.")
        return

    entry = {"enabled": True}
    if kind == 1:
        # choose weekday
        weekdays = ["Mon(0)", "Tue(1)", "Wed(2)", "Thu(3)", "Fri(4)", "Sat(5)", "Sun(6)"]
        await ctx.send("Chọn ngày trong tuần (nhập số 0-6):\n" + "\n".join(weekdays))
        try:
            msg = await bot.wait_for('message', check=check, timeout=60)
            day_choice = int(msg.content.strip())
            if day_choice < 0 or day_choice > 6:
                await ctx.send("Ngày không hợp lệ. Hủy.")
                return
            entry["day"] = day_choice
        except Exception:
            await ctx.send("Timeout hoặc đầu vào không hợp lệ. Hủy.")
            return
    else:
        # one-off date
        await ctx.send("Nhập ngày theo định dạng YYYY-MM-DD:")
        try:
            msg = await bot.wait_for('message', check=check, timeout=60)
            date_str = msg.content.strip()
            datetime.strptime(date_str, "%Y-%m-%d")
            entry["date"] = date_str
        except Exception:
            await ctx.send("Định dạng ngày không hợp lệ hoặc timeout. Hủy.")
            return

    # 3) choose time (offer suggestions from default schedule times)
    # collect unique times from DEFAULT_SCHEDULE
    suggested_times = []
    for ev in DEFAULT_SCHEDULE:
        t = ev.get("time")
        if t not in suggested_times:
            suggested_times.append(t)
    lines = [f"{i+1}. {t}" for i, t in enumerate(suggested_times)]
    lines.append(f"{len(lines)+1}. Nhập thời gian thủ công (HH:MM:SS)")
    await ctx.send("Chọn thời gian:\n" + "\n".join(lines))
    try:
        msg = await bot.wait_for('message', check=check, timeout=60)
        t_choice = int(msg.content.strip())
    except Exception:
        await ctx.send("Timeout hoặc đầu vào không hợp lệ. Hủy.")
        return

    if 1 <= t_choice <= len(suggested_times):
        entry["time"] = suggested_times[t_choice - 1]
    else:
        await ctx.send("Nhập thời gian theo HH:MM:SS:")
        try:
            msg = await bot.wait_for('message', check=check, timeout=60)
            time_str = msg.content.strip()
            datetime.strptime(time_str, "%H:%M:%S")
            entry["time"] = time_str
        except Exception:
            await ctx.send("Định dạng thời gian không hợp lệ hoặc timeout. Hủy.")
            return

    # 4) choose sound from sounds/ folder
    sound_files = [f for f in os.listdir("sounds") if os.path.isfile(os.path.join("sounds", f))]
    if not sound_files:
        await ctx.send("Không tìm thấy file âm thanh trong thư mục sounds/. Hủy.")
        return
    lines = [f"{i+1}. {fn}" for i, fn in enumerate(sound_files)]
    lines.append(f"{len(lines)+1}. Nhập tên file thủ công")
    await ctx.send("Chọn file âm thanh:\n" + "\n".join(lines))
    try:
        msg = await bot.wait_for('message', check=check, timeout=60)
        s_choice = int(msg.content.strip())
    except Exception:
        await ctx.send("Timeout hoặc đầu vào không hợp lệ. Hủy.")
        return

    if 1 <= s_choice <= len(sound_files):
        entry["sound"] = sound_files[s_choice - 1]
    else:
        await ctx.send("Nhập tên file (ví dụ welcome.ogg):")
        try:
            msg = await bot.wait_for('message', check=check, timeout=60)
            fname = msg.content.strip()
            if not os.path.exists(os.path.join("sounds", fname)):
                await ctx.send("File không tồn tại. Hủy.")
                return
            entry["sound"] = fname
        except Exception:
            await ctx.send("Timeout hoặc đầu vào không hợp lệ. Hủy.")
            return

    # set chosen channel
    entry["channel_id"] = chosen_channel_id
    SCHEDULE.append(entry)
    save_schedules()
    await ctx.send(f"Đã thêm lịch: {entry}")


@bot.command()
async def adddate(ctx, date_str: str, time_str: str, sound: str, channel_index: int = None):
    """Add a one-off schedule by date: `!adddate YYYY-MM-DD HH:MM:SS sound [channel_index]`"""
    # validate date
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        await ctx.send("Date must be in YYYY-MM-DD format.")
        return
    # validate time
    try:
        datetime.strptime(time_str, "%H:%M:%S")
    except Exception:
        await ctx.send("Time must be in HH:MM:SS format.")
        return
    if not sound.lower().endswith((".ogg", ".mp3", ".wav")):
        sound = f"{sound}.ogg"

    entry = {"date": date_str, "time": time_str, "sound": sound, "enabled": True}
    if channel_index is not None:
        vcs = [c for c in ctx.guild.channels if isinstance(c, discord.VoiceChannel)]
        if channel_index < 1 or channel_index > len(vcs):
            await ctx.send(f"Channel index invalid. Use `!listvoices` to get indices.")
            return
        entry["channel_id"] = vcs[channel_index - 1].id
    else:
        if ctx.author.voice and ctx.author.voice.channel:
            entry["channel_id"] = ctx.author.voice.channel.id

    SCHEDULE.append(entry)
    save_schedules()
    await ctx.send(f"Added one-off schedule #{len(SCHEDULE)}: date={date_str} time={time_str} sound={sound}")


@bot.command()
async def testvoice(ctx, index: int, sound: str = None):
    """Phát thử một file âm thanh vào voice channel theo chỉ số từ `!listvoices`"""
    vcs = [c for c in ctx.guild.channels if isinstance(c, discord.VoiceChannel)]
    if not vcs:
        await ctx.send("Không có voice channel để test.")
        return
    if index < 1 or index > len(vcs):
        await ctx.send(f"Vui lòng chọn index hợp lệ: 1 - {len(vcs)}")
        return
    channel = vcs[index - 1]
    if not sound:
        await ctx.send("Vui lòng cung cấp tên file âm thanh (ví dụ: welcome hoặc welcome.ogg)")
        return
    if not sound.lower().endswith((".ogg", ".mp3")):
        filename = f"{sound}.ogg"
    else:
        filename = sound
    await ctx.send(f"Đang phát `{filename}` vào kênh **{channel.name}**...")
    await play_sound(filename, channel)

@bot.command()
async def test(ctx, sound):
    # if user didn't provide extension, prefer .ogg then .mp3
    if not sound.lower().endswith((".ogg", ".mp3")):
        filename = f"{sound}.ogg"
    else:
        filename = sound
    await play_sound(filename)


@bot.command()
async def testpcm(ctx, sound):
    """Force PCM playback (bypass Opus passthrough)."""
    if not sound.lower().endswith((".ogg", ".mp3", ".wav")):
        filename = f"{sound}.ogg"
    else:
        filename = sound
    await play_sound(filename, force_pcm=True)


@bot.command()
async def testtone(ctx):
    """Play a short generated tone (tone_1k.wav)."""
    tone_file = os.path.join("sounds", "tone_1k.wav")
    if not os.path.exists(tone_file):
        await ctx.send("Tone file not found. Run the ffmpeg command locally to create sounds/tone_1k.wav")
        return
    await play_sound("tone_1k.wav")


@bot.command()
async def jointimer(ctx, index: int = None):
    """Join the voice channel: prefer author's current voice, or use index from !listvoices"""
    # determine target channel
    target = None
    if ctx.author.voice and ctx.author.voice.channel:
        target = ctx.author.voice.channel
    elif index is not None:
        vcs = [c for c in ctx.guild.channels if isinstance(c, discord.VoiceChannel)]
        if not vcs:
            await ctx.send("Không có voice channel trong server này.")
            return
        if index < 1 or index > len(vcs):
            await ctx.send(f"Index không hợp lệ. Chọn 1 - {len(vcs)}")
            return
        target = vcs[index - 1]
    else:
        await ctx.send("Bạn phải ở trong voice channel hoặc cung cấp index từ `!listvoices`.")
        return

    # connect
    existing_vc = discord.utils.get(bot.voice_clients, guild=target.guild)
    if existing_vc and existing_vc.channel.id == target.id and existing_vc.is_connected():
        await ctx.send(f"Đã kết nối tới **{target.name}**")
        return
    try:
        await target.connect()
        await ctx.send(f"Bot đã vào kênh **{target.name}**")
    except Exception as e:
        await ctx.send(f"Không thể kết nối: {e}")
        print(f"jointimer connect error: {e}")
        traceback.print_exc()


@bot.command()
async def timer(ctx, mode: str, index: int = None):
    """Control the scheduled timer: `!timer on [channel_index]` or `!timer off`.
    When enabling, if you are in voice the bot will use your voice channel; otherwise you can provide a voice index from `!listvoices`, or the bot will try to match text channel name to a voice channel."""
    global TIMER_ENABLED, VOICE_CHANNEL_ID
    mode = mode.lower()
    if mode == "on":
        # choose voice channel: explicit index, author's current voice, or match text channel name
        chosen_channel = None
        if index is not None:
            vcs = [c for c in ctx.guild.channels if isinstance(c, discord.VoiceChannel)]
            if index < 1 or index > len(vcs):
                await ctx.send(f"Index không hợp lệ. Chọn 1 - {len(vcs)}")
                return
            chosen_channel = vcs[index - 1]
        elif ctx.author.voice and ctx.author.voice.channel:
            chosen_channel = ctx.author.voice.channel
        else:
            # try to find a voice channel with same name as text channel
            text_name = getattr(ctx.channel, 'name', None)
            if text_name:
                for c in ctx.guild.channels:
                    if isinstance(c, discord.VoiceChannel) and c.name == text_name:
                        chosen_channel = c
                        break

        if chosen_channel:
            VOICE_CHANNEL_ID = chosen_channel.id
            await ctx.send(f"Timer sẽ phát vào voice channel: **{chosen_channel.name}**")
        else:
            if not VOICE_CHANNEL_ID:
                await ctx.send("Không xác định được voice channel — hãy join voice trước, hoặc cung cấp index: `!timer on <index>`.")
                return

        if check_schedule.is_running():
            await ctx.send("Timer đã đang chạy.")
            TIMER_ENABLED = True
            return
        check_schedule.start()
        TIMER_ENABLED = True
        await ctx.send("Timer đã bật.")
    elif mode == "off":
        if check_schedule.is_running():
            check_schedule.stop()
            TIMER_ENABLED = False
            await ctx.send("Timer đã tắt.")
        else:
            TIMER_ENABLED = False
            await ctx.send("Timer đã tắt (không chạy).")
    else:
        await ctx.send("Sử dụng: `!timer on [index]` hoặc `!timer off`")

async def start_health_server():
    async def handle(request):
        return web.Response(text="Bot is alive")
    app = web.Application()
    app.router.add_get("/", handle)
    port = int(os.environ.get("PORT", "3000"))
    runner = web.AppRunner(app)
    try:
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        print(f"Health server listening on 0.0.0.0:{port}")
    except Exception as e:
        print(f"Health server failed to start: {e}")

# schedule health server to start in the bot's event loop so Render sees a bound port
try:
    bot.loop.create_task(start_health_server())
except Exception as e:
    print(f"Failed to schedule health server task: {e}")

bot.run(TOKEN)


@bot.event
async def on_message(message):
    # show quick command hint when user sends a lone '!'
    if message.author.bot:
        return
    if message.content.strip() == "!":
        help_lines = [
            "Lệnh gợi ý:",
            "!listschedule - xem các lịch",
            "!listschedule để xem index, !toggleschedule <index>",
            "!setschedulechannel <index> (ở voice) - gán kênh cho lịch",
            "!adddate YYYY-MM-DD HH:MM:SS sound [channel_index] - thêm lịch 1 lần",
            "!addschedule <day 0-6> HH:MM:SS sound - thêm lịch định kỳ",
            "!timer on [index] - bật timer, sử dụng kênh voice hiện tại hoặc index",
            "!timer off - tắt timer",
            "!test <sound>, !testpcm <sound>, !testtone"
        ]
        try:
            await message.channel.send("\n".join(help_lines))
        except Exception:
            pass
        return

    await bot.process_commands(message)