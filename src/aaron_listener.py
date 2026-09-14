"""
Lightweight, always-on Telegram listener. This is the ONLY thing that needs
to already be running for you to remotely start Aaron (guard_watch.py) from
your phone - it never touches the webcam or does any detection itself, it
just polls Telegram and starts/stops guard_watch.py as a subprocess.

Commands (only from the chat_id in telegram_config.json):
    /wake   - start Aaron if he isn't already running
    /sleep  - stop Aaron if he's running
    /status - is Aaron currently running?
    /help   - list commands

Everything else (/sit /guard /snapshot /lock, guard_watch.py's own /status
and /help) gets relayed to Aaron via a local file - guard_watch.py watches
for it. This listener is the ONLY thing that calls Telegram's getUpdates;
guard_watch.py used to poll it too, which caused a race where whichever
process happened to grab an update first would "steal" it even if it didn't
understand that command - the classic "valid command, no response" bug.
Routing everything through one poller fixes that.

Meant to be launched via pythonw.exe (no console window). See
run_listener_hidden.vbs and stop_listener.bat.
"""

import json
import os
import random
import subprocess
import time
from datetime import datetime
import psutil
import requests

import paths

SCRIPT_DIR = paths.SRC_DIR
CONFIG_PATH = paths.private("telegram_config.json")
LOG_PATH = paths.log_file("aaron_listener.log")
GUARD_SCRIPT = os.path.join(paths.SRC_DIR, "guard_watch.py")
PYTHONW = os.path.join(paths.PROJECT_DIR, "venv", "Scripts", "pythonw.exe")
GUARD_COMMAND_PATH = paths.private("guard_command.json")

# Commands this listener handles itself - everything else gets relayed to
# guard_watch.py instead of being treated as unknown.
LISTENER_COMMANDS = {"/wake", "/sleep", "/fetch"}

TELEGRAM_POLL_TIMEOUT = 25
CREATE_NO_WINDOW = 0x08000000

# Friend-only "play" commands - purely canned fun replies, completely
# separate from the real command set (never touches handle_command or
# relay_to_guard), so there's zero control surface here, just toys.
PLAY_COMMANDS = {
    "/pet": [
        "🐕 *tail wagging intensifies* Aaron loves pets!",
        "🐕 *leans into your hand* good spot, right there.",
        "🐕 *happy dog noises* more please!!",
    ],
    "/treat": [
        "🐕 *nom nom nom* Aaron devours the treat happily!",
        "🐕 *catches it out of the air* nice throw!",
        "🐕 *does a little spin for another one*",
    ],
    "/goodboy": [
        "🐕 *rolls over, very proud* best boy confirmed.",
        "🐕 *puffs chest out* he knows.",
        "🐕 *wags entire body, not just the tail*",
    ],
}

DOG_FACTS = [
    "🐾 Dog fact: a dog's nose print is as unique as a human fingerprint.",
    "🐾 Dog fact: dogs can smell roughly 10,000 to 100,000 times better than humans.",
    "🐾 Dog fact: the Basenji is a dog breed that doesn't bark - it yodels instead.",
    "🐾 Dog joke: why did the dog sit in the shade? Didn't want to be a hot dog.",
    "🐾 Dog fact: puppies are born deaf, blind, and toothless.",
    "🐾 Dog joke: what do you call a dog that can do magic? A labracadabrador.",
    "🐾 Dog fact: a dog's sense of time is thought to be linked to smell fading over hours.",
    "🐾 Dog joke: why don't dogs make good dancers? They have two left feet... and two right.",
    "🐾 Dog fact: three dogs survived the Titanic sinking.",
    "🐾 Dog fact: dogs curl up in a ball when sleeping as an instinct to protect vital organs.",
]


def log(message):
    line = f"{datetime.now().isoformat(timespec='seconds')} [Aaron-listener] {message}"
    print(line)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def load_telegram_config():
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    if not config.get("bot_token") or "PASTE" in config["bot_token"]:
        raise RuntimeError(f"Fill in your real bot token and chat_id in {CONFIG_PATH} first.")
    friends = {k: str(v) for k, v in config.get("friends", {}).items()}
    return config["bot_token"], str(config["chat_id"]), friends


def build_command_keyboard():
    """A persistent reply keyboard - tapping a button just sends its label
    as a normal text message, so this needs zero changes to how commands
    are parsed/routed elsewhere. Stays visible in the chat until replaced
    or dismissed, so it only needs to be attached occasionally, not on
    every single message."""
    return {
        "keyboard": [
            ["/wake", "/sleep", "/status"],
            ["/sit", "/guard", "/snapshot"],
            ["/watch", "/stopwatch", "/lock"],
            ["/fetch", "/help"],
        ],
        "resize_keyboard": True,
    }


def build_friend_keyboard():
    """Friends get their own persistent keyboard with ONLY the sandboxed
    play commands - visually distinct from the owner's real controls, and
    tapping any of these still only ever reaches the harmless canned-reply
    branch, never handle_command or relay_to_guard."""
    return {
        "keyboard": [["/pet", "/treat", "/goodboy"]],
        "resize_keyboard": True,
    }


def send_telegram_message(bot_token, chat_id, text, keyboard=True):
    """keyboard: True = owner's real command keyboard, "friend" = the
    play-only keyboard, False = no keyboard change."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = {"chat_id": chat_id, "text": text}
    if keyboard == "friend":
        data["reply_markup"] = json.dumps(build_friend_keyboard())
    elif keyboard:
        data["reply_markup"] = json.dumps(build_command_keyboard())
    try:
        resp = requests.post(url, data=data, timeout=10)
        if not resp.ok:
            log(f"Telegram send failed: {resp.status_code} {resp.text}")
    except requests.RequestException as e:
        log(f"Telegram send error: {e}")


def answer_callback_query(bot_token, callback_query_id, text=None):
    """Acknowledges a button tap - required so Telegram stops showing the
    button's loading spinner. `text` shows as a small popup on the phone."""
    url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
    data = {"callback_query_id": callback_query_id}
    if text:
        data["text"] = text
    try:
        resp = requests.post(url, data=data, timeout=10)
        if not resp.ok:
            log(f"answerCallbackQuery failed: {resp.status_code} {resp.text}")
    except requests.RequestException as e:
        log(f"answerCallbackQuery error: {e}")


def send_telegram_sticker(bot_token, chat_id, file_id):
    # Resending a sticker just needs its file_id - no re-upload needed.
    url = f"https://api.telegram.org/bot{bot_token}/sendSticker"
    try:
        resp = requests.post(url, data={"chat_id": chat_id, "sticker": file_id}, timeout=10)
        if not resp.ok:
            log(f"Telegram sticker send failed: {resp.status_code} {resp.text}")
    except requests.RequestException as e:
        log(f"Telegram sticker send error: {e}")


def send_telegram_photo_by_id(bot_token, chat_id, file_id):
    # Same idea as the sticker forward - reuse the file_id, no re-upload.
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    try:
        resp = requests.post(url, data={"chat_id": chat_id, "photo": file_id}, timeout=10)
        if not resp.ok:
            log(f"Telegram photo forward failed: {resp.status_code} {resp.text}")
    except requests.RequestException as e:
        log(f"Telegram photo forward error: {e}")


def send_telegram_animation_by_id(bot_token, chat_id, file_id):
    # GIFs sent through Telegram arrive as "animation", not "photo".
    url = f"https://api.telegram.org/bot{bot_token}/sendAnimation"
    try:
        resp = requests.post(url, data={"chat_id": chat_id, "animation": file_id}, timeout=10)
        if not resp.ok:
            log(f"Telegram animation forward failed: {resp.status_code} {resp.text}")
    except requests.RequestException as e:
        log(f"Telegram animation forward error: {e}")


def find_guard_pids():
    """PIDs of any pythonw.exe process running guard_watch.py, no matter how
    it was started (this listener, the desktop shortcut, run.bat, ...).

    Uses psutil (in-process) instead of spawning powershell.exe - the old
    Get-CimInstance approach cost ~0.5s per call just for PowerShell's own
    startup, which sat directly in the /wake and voice-wake trigger path.
    psutil does the same check in ~0.02s."""
    pids = []
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            if proc.info["name"] != "pythonw.exe":
                continue
            cmdline = proc.info["cmdline"] or []
            if any("guard_watch.py" in part for part in cmdline):
                pids.append(proc.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return pids


class GuardHandle:
    """Starts/stops Aaron by looking at what's ACTUALLY running on the
    system, not just what this listener itself launched - so /sleep works
    even if Aaron was started manually (desktop shortcut, run.bat, etc)."""

    def is_running(self):
        return len(find_guard_pids()) > 0

    def start(self):
        if self.is_running():
            return False
        subprocess.Popen([PYTHONW, GUARD_SCRIPT], cwd=SCRIPT_DIR, creationflags=CREATE_NO_WINDOW)
        return True

    def stop(self):
        pids = find_guard_pids()
        if not pids:
            return False
        for pid in pids:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                            capture_output=True, creationflags=CREATE_NO_WINDOW)
        return True


def relay_to_guard(text):
    """Hands a command off to guard_watch.py via a small local file it
    watches - keeps Telegram polling to exactly one process (this one)."""
    with open(GUARD_COMMAND_PATH, "w") as f:
        json.dump({"id": time.time_ns(), "text": text}, f)


def handle_command(text, bot_token, chat_id, guard, friends):
    text = text.strip().lower()

    if text not in LISTENER_COMMANDS and text not in ("/status", "/help"):
        if guard.is_running():
            relay_to_guard(text)
            log(f"Relayed '{text}' to Aaron.")
        else:
            send_telegram_message(bot_token, chat_id,
                                   "🐕💤 Aaron is sleeping soundly right now. Send /wake to rouse him first.")
        return

    if text == "/fetch":
        barked_at = []
        not_ready = []
        for name, friend_chat_id in friends.items():
            if not friend_chat_id or "PASTE" in friend_chat_id:
                not_ready.append(name)
                continue
            send_telegram_message(bot_token, friend_chat_id, "AWOOOOOOOOOOOOOOOOOFFF", keyboard="friend")
            barked_at.append(name)

        if barked_at:
            log(f"Sent /fetch bark to: {', '.join(barked_at)}.")
            send_telegram_message(bot_token, chat_id, f"🐕 Fetched! Sent the bark to: {', '.join(barked_at)}.")
        if not_ready:
            send_telegram_message(
                bot_token, chat_id,
                f"(Skipped - no chat_id set up yet: {', '.join(not_ready)})",
            )
        if not friends:
            send_telegram_message(bot_token, chat_id, "No friends configured in telegram_config.json yet.")

    elif text == "/wake":
        if guard.start():
            log("Started Aaron (remote /wake).")
            send_telegram_message(bot_token, chat_id, "🐕 Aaron is waking up and heading to guard duty.")
        else:
            send_telegram_message(bot_token, chat_id, "🐕 Aaron's already on duty.")

    elif text == "/sleep":
        if guard.stop():
            log("Stopped Aaron (remote /sleep).")
            send_telegram_message(bot_token, chat_id, "🐕 Aaron is heading home to sleep.")
        else:
            send_telegram_message(bot_token, chat_id, "Aaron wasn't running.")

    elif text == "/status":
        running = guard.is_running()
        state = "on duty 🐕👀" if running else "not running 💤"
        send_telegram_message(bot_token, chat_id, f"Aaron is currently: {state}")
        if running:
            # Also relay so guard_watch.py reports its own armed/resting detail.
            relay_to_guard(text)

    elif text == "/help":
        send_telegram_message(
            bot_token, chat_id,
            "🐕 Listener commands (work anytime, whether or not Aaron is running):\n"
            "/wake - start Aaron\n"
            "/sleep - stop Aaron, however he was started\n"
            "/status - is he running right now?\n"
            "/fetch - AWOOOOOOOOOOOOOOOOOFFF at everyone in your friends list\n"
            "/help - this message\n\n"
            "Once Aaron is awake, he answers these directly:\n"
            "/sit - pause guarding\n"
            "/guard - resume guarding\n"
            "/status - is he guarding or resting?\n"
            "/snapshot - live photo from the camera\n"
            "/watch - pseudo-live view, refreshes every ~2s for up to 2 min\n"
            "/stopwatch - end an active /watch early\n"
            "/lock - lock the PC right now\n"
            "/help - his own command list",
        )


def main():
    log("Listener starting.")

    try:
        bot_token, chat_id, friends = load_telegram_config()
    except (FileNotFoundError, RuntimeError) as e:
        log(str(e))
        return

    guard = GuardHandle()
    base_url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    offset = None
    waiting_friends = set()  # chat_ids told "he's asleep", to notify once he wakes
    was_running = guard.is_running()

    # Discard commands queued before this run started.
    try:
        resp = requests.get(base_url, params={"timeout": 0}, timeout=10)
        results = resp.json().get("result", [])
        if results:
            offset = results[-1]["update_id"] + 1
    except requests.RequestException as e:
        log(f"Startup poll failed: {e}")

    log("Listener ready.")
    send_telegram_message(bot_token, chat_id, "🐕 Aaron's listener is online. Tap a button below, or type a command.")

    while True:
        try:
            params = {"timeout": TELEGRAM_POLL_TIMEOUT}
            if offset is not None:
                params["offset"] = offset
            resp = requests.get(base_url, params=params, timeout=TELEGRAM_POLL_TIMEOUT + 10)
            data = resp.json()

            for update in data.get("result", []):
                offset = update["update_id"] + 1

                callback = update.get("callback_query")
                if callback:
                    cq_chat_id = str(callback.get("from", {}).get("id", ""))
                    cq_data = callback.get("data", "")
                    if cq_chat_id == chat_id and cq_data in ("triage_ok", "triage_lock"):
                        relay_to_guard(f"__{cq_data}__")
                        log(f"Relayed triage decision '{cq_data}' to Aaron.")
                        answer_callback_query(bot_token, callback["id"],
                                               "Standing down" if cq_data == "triage_ok" else "Locking now")
                    else:
                        answer_callback_query(bot_token, callback["id"])
                    continue

                message = update.get("message") or update.get("edited_message")
                if not message:
                    continue
                chat = message.get("chat", {})
                msg_chat_id = str(chat.get("id", ""))
                if msg_chat_id != chat_id:
                    username = chat.get("username", "?")
                    name = chat.get("first_name", "?")
                    text = message.get("text", "")
                    sticker = message.get("sticker")
                    photo = message.get("photo")
                    animation = message.get("animation")

                    play_reply = PLAY_COMMANDS.get(text.strip().lower())
                    if play_reply:
                        send_telegram_message(bot_token, msg_chat_id, random.choice(play_reply), keyboard="friend")
                        log(f"Played '{text.strip().lower()}' with {name} (@{username}).")
                        send_telegram_message(bot_token, chat_id, f"🐕 {name} (@{username}) played {text.strip().lower()} with Aaron.")
                        continue

                    if sticker:
                        emoji = sticker.get("emoji", "")
                        log(f"Sticker from unrecognized chat (relayed to owner) - id={msg_chat_id} "
                            f"username=@{username} name={name} emoji={emoji}")
                        send_telegram_message(bot_token, chat_id, f"🐕 {name} (@{username}) sent Aaron a sticker {emoji}")
                        send_telegram_sticker(bot_token, chat_id, sticker["file_id"])
                    elif photo:
                        caption = message.get("caption", "")
                        log(f"Photo from unrecognized chat (relayed to owner) - id={msg_chat_id} "
                            f"username=@{username} name={name} caption={caption!r}")
                        label = f"🐕 {name} (@{username}) sent Aaron a photo"
                        if caption:
                            label += f': "{caption}"'
                        send_telegram_message(bot_token, chat_id, label)
                        send_telegram_photo_by_id(bot_token, chat_id, photo[-1]["file_id"])  # largest size
                    elif animation:
                        caption = message.get("caption", "")
                        log(f"GIF from unrecognized chat (relayed to owner) - id={msg_chat_id} "
                            f"username=@{username} name={name} caption={caption!r}")
                        label = f"🐕 {name} (@{username}) sent Aaron a GIF"
                        if caption:
                            label += f': "{caption}"'
                        send_telegram_message(bot_token, chat_id, label)
                        send_telegram_animation_by_id(bot_token, chat_id, animation["file_id"])
                    elif text:
                        log(f"Message from unrecognized chat (relayed to owner) - id={msg_chat_id} "
                            f"username=@{username} name={name} text={text!r}")
                        send_telegram_message(bot_token, chat_id, f"🐕 {name} (@{username}) said to Aaron: {text}")
                    else:
                        # voice / video / document / etc - not relayed yet
                        log(f"Unsupported message type from unrecognized chat (NOT relayed) - "
                            f"id={msg_chat_id} username=@{username} name={name} keys={list(message.keys())}")
                        send_telegram_message(
                            bot_token, chat_id,
                            f"🐕 {name} (@{username}) sent Aaron something (voice/video/document/etc) "
                            f"that isn't relayed yet - check the bot chat directly.",
                        )
                    if not guard.is_running() and msg_chat_id not in waiting_friends:
                        waiting_friends.add(msg_chat_id)
                        send_telegram_message(
                            bot_token, msg_chat_id,
                            "🐕 Aaron is asleep right now. I'll let you know when he wakes up!\n\n"
                            f"{random.choice(DOG_FACTS)}\n\n"
                            "(try /pet, /treat, or /goodboy while you wait)",
                            keyboard="friend",
                        )
                        log(f"Told {name} (@{username}) Aaron is asleep - added to wake-notify list.")
                    continue
                text = message.get("text")
                if text:
                    handle_command(text, bot_token, chat_id, guard, friends)

            # Notify anyone waiting the moment Aaron actually wakes up,
            # regardless of what/who started him (command, shortcut, etc).
            now_running = guard.is_running()
            if now_running and not was_running and waiting_friends:
                for friend_chat_id in waiting_friends:
                    send_telegram_message(bot_token, friend_chat_id, "🐕 Aaron just woke up!", keyboard="friend")
                log(f"Notified {len(waiting_friends)} waiting friend(s) that Aaron woke up.")
                waiting_friends.clear()
            was_running = now_running
        except requests.RequestException as e:
            log(f"Poll error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
