# Aaron - Telegram Commands & Buttons

This document lists every Telegram bot command and interactive button. All commands go through aaron_listener.py (the only process that polls Telegram). Certain commands are handled by the listener itself, while others are relayed to guard_watch.py.

## Command Routing

```
Telegram Bot API
       │
       ├─ Only aaron_listener.py polls
       │
       ├─ Listener handles: /wake, /sleep, /fetch, /status*, /help*
       │
       └─ Listener relays to guard_watch.py: /sit, /guard, /snapshot, /watch, /stopwatch, /lock
          (via private/guard_command.json)
```

**/status** and **/help** have special handling:
- Listener always responds with its own message (showing guard running state)
- If guard is running, listener also relays /status to guard so it reports armed/resting detail

---

## Listener Commands (Handle Only If Aaron Is Asleep)

These commands work whether or not guard_watch.py is running. They are handled entirely by aaron_listener.py.

### /wake

- **Who can use**: Owner only (chat_id in telegram_config.json)
- **What it does**: Starts guard_watch.py if not already running
- **Response**: 
  - If guard was stopped: "🐕 Aaron is waking up and heading to guard duty."
  - If already running: "🐕 Aaron's already on duty."
- **Side effect**: Starts guard_watch.py as a hidden subprocess (pythonw.exe, no window)
- **Example use**: You left home but forgot to start Aaron; send /wake from your phone

### /sleep

- **Who can use**: Owner only
- **What it does**: Stops guard_watch.py completely (terminates subprocess)
- **Response**:
  - If guard was running: "🐕 Aaron is heading home to sleep."
  - If not running: "Aaron wasn't running."
- **Side effect**: Kills the guard process immediately
- **Example use**: You're about to have a repair person over; send /sleep so Aaron doesn't lock the desk

### /status

- **Who can use**: Owner only
- **What it does**: 
  - Listener responds immediately with guard's running state
  - If guard is running, listener also relays /status to guard for detailed response
- **Listener Response**: "Aaron is currently: on duty 🐕👀" (or "not running 💤")
- **Guard Response** (if running): "Aaron is currently: on guard, watching the desk 🐕👀" (or "resting (paused) 🐾💤") + lock state note
- **Example use**: Check if Aaron is watching

### /fetch

- **Who can use**: Owner only
- **What it does**: Sends "AWOOOOOOOOOOOOOOOOOFFF" to every friend in telegram_config.json's friends list
- **Response**: 
  - Owner gets: "🐕 Fetched! Sent the bark to: [friend names]." (or notes if some aren't configured)
  - Each friend gets the bark + friend keyboard (for /pet, /treat, /goodboy)
- **Side effect**: Friends see Aaron is active; they can respond with play commands
- **Example use**: You want to remind your friends Aaron exists, or playfully startle them

### /help

- **Who can use**: Owner only
- **What it does**: Shows all available commands
- **Response**: Comprehensive help message covering:
  - Listener commands (work anytime)
  - Guard commands (work when Aaron is running)
  - Pseudo-live view timeout info
  - Triage grace period info

---

## Guard Commands (Relayed If Aaron Is Awake)

These commands only work when guard_watch.py is running. If you send one while Aaron is asleep, the listener responds: "🐕💤 Aaron is sleeping soundly right now. Send /wake to rouse him first."

All except **/status** and **/help** are relayed to guard_watch.py via private/guard_command.json.

### /sit

- **Who can use**: Owner only
- **What it does**: Pauses guarding (camera keeps running, but won't lock on unknown faces)
- **Response**: "🐕 Aaron lies down. Guarding paused - send /guard to wake him up."
- **Use case**: A friend is sitting next to you; don't want him locked out

### /guard (or /start)

- **Who can use**: Owner only
- **What it does**: Resumes active guarding (opposite of /sit)
- **Response**: "🐕 Aaron hops back up. Back on guard!"
- **Use case**: Friend left; resume security

### /snapshot

- **Who can use**: Owner only
- **What it does**: Get a single photo of what the camera sees right now
- **Response**: A photo with caption "🐕 Here's what Aaron sees right now." (or "No camera frame available yet - try again in a second.")
- **Use case**: Quickly check what's at your desk

### /watch

- **Who can use**: Owner only
- **What it does**: Start pseudo-live view (refreshes the same photo every ~2 seconds for up to 2 minutes)
- **Response**: Sends initial photo with caption "🐕 Live watch started - updates every couple seconds. Send /stopwatch to end early."
- **Then**: Updates the same message in place every 2 seconds with a new photo + timestamp
- **Timeout**: Stops automatically after 120 seconds with "🐕 Live watch timed out after 2 minutes. Send /watch again if you need more."
- **Use case**: Monitor what's happening at your desk in near-real-time (e.g., waiting for a delivery)
- **Note**: Telegram API limitation: you can only edit a message's photo so many times before Telegram throttles. Refreshing for 2 minutes is safe; longer sessions might hit rate limits.

### /stopwatch

- **Who can use**: Owner only
- **What it does**: End an active /watch session early (stops refreshing)
- **Response**: "🐕 Stopped watching." (or "Wasn't watching." if no watch was active)
- **Use case**: You're done monitoring; stop the live feed

### /lock

- **Who can use**: Owner only
- **What it does**: Lock the PC immediately (regardless of guard state)
- **Response**: "🔒 Locking your PC now."
- **Side effect**: Calls Windows' LockWorkStation API
- **Use case**: Immediate lock without waiting for intrusion detection

### /help

- **Who can use**: Owner only (when relayed to guard)
- **What it does**: Guard displays its own command list
- **Response**: Command reference showing /guard, /sit, /status, /snapshot, /watch, /stopwatch, /lock, /help
- **Also shows**: Triage grace period (10 seconds) and that /sleep can be sent to the listener to stop Aaron entirely

---

## Triage Buttons (Automatic, Not User-Initiated)

When guard_watch.py detects a face that somewhat resembles someone in your training data but isn't confident enough (score between TRIAGE_FLOOR and COSINE_THRESHOLD), it sends a photo with two buttons:

### Photo Caption

"🐕 Aaron spotted someone he don't know. Is this someone you know? No response in 10s and he'll lock automatically."

### Buttons

#### ✅ I know them (triage_ok)

- **Effect**: Confirms the person is legitimate (trained person under bad lighting/angle, or someone you know who isn't in the training data)
- **Guard's Action**: Cancels lock, clears the unknown streak, resumes guarding
- **Response**: "🐕 Got it, standing down. Back on guard."

#### 🔒 Lock now (triage_lock)

- **Effect**: Override the triage and lock immediately anyway
- **Guard's Action**: Locks the PC right now
- **Response**: "🔒 Locking your PC now."

### Auto-Timeout

If you don't tap a button within 10 seconds (TRIAGE_GRACE_SECONDS), guard_watch.py locks automatically:
- **Response**: "🐕 No response - locking your PC now (better safe than sorry)."
- **Alarm**: Plays alarm sound (if alarm.wav exists in misc/ and speaker output is available)

---

## Friend Commands (Non-Owner Chat IDs)

Friends (chat_ids in telegram_config.json's "friends" dict) see a different keyboard with harmless play commands. These are purely for fun and don't affect security.

### /pet

- **Response**: Random from:
  - "🐕 *tail wagging intensifies* Aaron loves pets!"
  - "🐕 *leans into your hand* good spot, right there."
  - "🐕 *happy dog noises* more please!!"
- **Side effect**: Owner is notified: "🐕 [Friend] (friend_username) played /pet with Aaron."

### /treat

- **Response**: Random from:
  - "🐕 *nom nom nom* Aaron devours the treat happily!"
  - "🐕 *catches it out of the air* nice throw!"
  - "🐕 *does a little spin for another one*"
- **Side effect**: Owner is notified: "🐕 [Friend] (friend_username) played /treat with Aaron."

### /goodboy

- **Response**: Random from:
  - "🐕 *rolls over, very proud* best boy confirmed."
  - "🐕 *puffs chest out* he knows."
  - "🐕 *wags entire body, not just the tail*"
- **Side effect**: Owner is notified: "🐕 [Friend] (friend_username) played /goodboy with Aaron."

### Friend-Initiated Messages

When a friend sends Aaron anything (text, sticker, photo, GIF):
- **Friend sees**: "🐕 Aaron is asleep right now. I'll let you know when he wakes up!" + random dog fact
- **Owner is notified**: "🐕 [Friend] (friend_username) sent Aaron [text/sticker/photo/GIF]" + the content relayed back
- **When Aaron wakes**: Friend gets "🐕 Aaron just woke up!" (one notification, regardless of how many messages they sent)

---

## Message Relay to Owner

When a non-owner sends Aaron a message, the listener relays it to the owner:

### Text Messages

**Friend sends**: "Hello Aaron! What's up?"

**Owner receives**: "🐕 [Friend] (friend_username) said to Aaron: Hello Aaron! What's up?"

### Stickers

**Friend sends**: A sticker

**Owner receives**: "🐕 [Friend] (friend_username) sent Aaron a sticker [emoji]"
- Also forwards the sticker (reusing Telegram's file_id, no re-upload)

### Photos

**Friend sends**: A photo (optionally with caption)

**Owner receives**: "🐕 [Friend] (friend_username) sent Aaron a photo[: caption]"
- Also forwards the largest version (reusing file_id)

### GIFs/Animations

**Friend sends**: A GIF

**Owner receives**: "🐕 [Friend] (friend_username) sent Aaron a GIF[: caption]"
- Also forwards the GIF (reusing file_id)

### Unsupported Content

**Friend sends**: Voice message, video, document, etc.

**Owner receives**: "🐕 [Friend] (friend_username) sent Aaron something (voice/video/document/etc) that isn't relayed yet - check the bot chat directly."
- Not forwarded (would require downloading/re-uploading; future enhancement)

---

## Built-In Keyboard

When the listener sends a message to the owner, it attaches the command keyboard:

```
/wake         /sleep        /status
/sit          /guard        /snapshot
/watch        /stopwatch    /lock
/fetch        /help
```

This keyboard is persistent (stays visible in the chat) and doesn't need to be resent on every message. Tapping a button just sends the command as normal text, so all the routing logic above applies.

Friends see a separate keyboard:

```
/pet          /treat        /goodboy
```

---

## Error Handling

### Invalid Command

**Owner sends**: "/unknown"

**Response**: "Woof? Unknown command. Try /help"

### Telegram API Error

If the bot fails to send a message/photo (network error, API issue, etc.):
- Log entry in `private/logs/aaron_listener.log` or `private/logs/guard_watch.log`
- Notification is silently dropped (no retry, no exception visible to user)
- Logs will show: "Telegram send failed: 500 Internal Server Error" or similar

### No Camera Frame

If guard_watch.py hasn't captured a frame yet (shouldn't happen, but possible on instant /snapshot right after startup):

**Response**: "No camera frame available yet - try again in a second."

### Aaron Asleep But Command Sent

**Owner sends any guard command** (e.g., /sit):

**Response**: "🐕💤 Aaron is sleeping soundly right now. Send /wake to rouse him first."

---

## Security Notes

- **Token & Chat ID**: Never share your telegram_config.json (contains bot_token and chat_ids)
- **Owner vs. Friends**: Only the chat_id listed as "chat_id" (not in "friends" dict) can issue real commands (/wake, /guard, /lock, /snapshot); friends see a play-only keyboard and can't control the guard
- **Callback Button Security**: Triage buttons are validated: only the owner's chat_id can approve/lock; other chat_ids' button taps are silently ignored
- **Photo Relay**: Friends' photos are relayed with their username visible in the message; owner can trace who sent what

---

## Quick Reference

| Command | Who | Guard Awake? | What | Handler |
|---------|-----|--------------|------|---------|
| /wake | Owner | Any | Start guard | Listener |
| /sleep | Owner | Any | Stop guard | Listener |
| /status | Owner | Any | Check state | Listener (+ Guard if running) |
| /fetch | Owner | Any | Bark at friends | Listener |
| /help | Owner | Any | List commands | Listener |
| /sit | Owner | Yes | Pause guarding | Guard |
| /guard | Owner | Yes | Resume guarding | Guard |
| /snapshot | Owner | Yes | Single photo | Guard |
| /watch | Owner | Yes | Live view (2min) | Guard |
| /stopwatch | Owner | Yes | End live view | Guard |
| /lock | Owner | Yes | Lock now | Guard |
| /help | Owner | Yes | Guard's help | Guard |
| /pet | Friend | Any | Play (canned) | Listener |
| /treat | Friend | Any | Play (canned) | Listener |
| /goodboy | Friend | Any | Play (canned) | Listener |
| Triage OK | Owner (button) | Yes | Confirm person | Guard |
| Triage Lock | Owner (button) | Yes | Lock now | Guard |

---

## Testing Commands

1. **Verify bot is reachable**: Send `/help` → should get response
2. **Test wake/sleep**: `/wake` → process starts; `/status` → "on duty"; `/sleep` → process stops; `/status` → "not running"
3. **Test guard commands** (after `/wake`): `/sit` → pauses; `/guard` → resumes; `/lock` → PC locks
4. **Test snapshot**: `/snapshot` → should get a photo (or "No camera frame" if startup lag)
5. **Test live view**: `/watch` → photo appears; wait 2s, photo refreshes; `/stopwatch` → stops
6. **Test triage**: Configure a person with bad lighting, deliberately stand in bad light until triage fires → tap buttons to confirm/dismiss
7. **Test friend keyboard**: Ask a friend to send a message → should see /pet, /treat, /goodboy buttons in their chat with Aaron
