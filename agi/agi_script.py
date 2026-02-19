#!/home/devesh/ai-asterisk/venv312/bin/python3
"""
Lucy AGI Script - FIXED VERSION
Fixes:
1. STREAM FILE now uses absolute path (no more result=-1 / 510 errors)
2. Recording uses s=2 (2 second silence auto-stop) for natural conversation
3. Better silence detection threshold
4. Proper turn flow: play greeting → record → transcribe → respond → loop
5. Removed retry logic that was causing double-reads
"""

import sys, os, time, traceback, select

BASE       = "/home/devesh/ai-asterisk"
SOUNDS_DIR = "/var/lib/asterisk/sounds"
REC_DIR    = "/tmp"
LOG_FILE   = "/tmp/agi_debug.log"

sys.path.append(BASE)
from ai_logic.groq_ai_enhanced import get_groq_response, reset_conversation, transcribe_audio_groq
from tts.tts_piper import text_to_speech

def log(msg):
    ts = time.strftime('%H:%M:%S')
    line = f"{ts} {msg}\n"
    with open(LOG_FILE, "a") as f:
        f.write(line)
    # Also print to stderr so it shows in asterisk console
    print(line, end="", file=sys.stderr)

def agi_read():
    line = sys.stdin.readline().rstrip('\r\n')
    log(f"RECV: [{line}]")
    return line

def agi_send(cmd):
    sys.stdout.write(cmd + "\n")
    sys.stdout.flush()
    log(f"SENT: {cmd}")

def agi(cmd, read_response=True):
    agi_send(cmd)
    if read_response:
        return agi_read()
    return ""

def drain_pipe():
    """Drain any unread AGI environment variables"""
    count = 0
    while True:
        ready = select.select([sys.stdin], [], [], 0.3)
        if not ready[0]:
            break
        line = sys.stdin.readline().rstrip('\r\n')
        if line:
            log(f"DRAIN: [{line}]")
            count += 1
    log(f"PIPE CLEAN (drained {count} lines)")

def wait_for_wav(wav_path, max_wait=10.0):
    """Wait for WAV file to appear and stabilize"""
    waited = 0.0
    last_size = -1
    while waited < max_wait:
        if os.path.exists(wav_path):
            size = os.path.getsize(wav_path)
            if size > 100 and size == last_size:
                return True
            last_size = size
        time.sleep(0.2)
        waited += 0.2
    return os.path.exists(wav_path) and os.path.getsize(wav_path) > 100

def say(text):
    """
    Generate TTS and stream to caller.
    
    CRITICAL FIX: Use absolute path with STREAM FILE.
    Old code computed a relative path like 'hi/ai_reply_123' which Asterisk 
    couldn't always resolve. Now we use the absolute path directly.
    Asterisk AGI's STREAM FILE accepts absolute paths starting with /
    """
    try:
        # Generate TTS - returns absolute path WITHOUT .wav
        abs_path = text_to_speech(text)
        wav_file = abs_path + ".wav"

        log(f"TTS generated: {abs_path}")

        if not wait_for_wav(wav_file):
            log(f"TTS ERROR: WAV never appeared: {wav_file}")
            return "200 result=-1"

        size = os.path.getsize(wav_file)
        log(f"TTS ready: {wav_file} ({size} bytes)")

        # Ensure Asterisk can read it
        try:
            os.chmod(wav_file, 0o644)
        except:
            pass

        # FIX: Use absolute path directly in STREAM FILE
        # Asterisk AGI supports absolute paths - no need for relative path magic
        log(f"STREAMING (absolute path): {abs_path}")
        result = agi(f'STREAM FILE {abs_path} ""')
        log(f"STREAM result: {result}")

        # Handle 510 error (command not understood - shouldn't happen with absolute path)
        if "510" in result:
            log("510 error on STREAM FILE - trying with EXEC Playback as fallback")
            # Fallback: use EXEC Playback (plays ulaw/slin/wav automatically)
            result2 = agi(f'EXEC Playback {abs_path}')
            log(f"Playback fallback result: {result2}")
            return result2

        return result

    except Exception as e:
        log(f"TTS/STREAM ERROR: {e}\n{traceback.format_exc()}")
        return "200 result=-1"

def record_audio(rec_path, max_silence_sec=2, max_duration_sec=15):
    """
    Record caller's speech.
    
    FIXES:
    1. Added s={silence} parameter - stops recording after N seconds of silence
       This is why recording was ending too fast before (it wasn't - RECORD was 
       returning -1 meaning it started but we weren't waiting properly)
    2. Proper file wait loop
    3. Returns (success, wav_path)
    
    Asterisk RECORD FILE syntax:
    RECORD FILE <filename> <format> <escape_digits> <timeout_ms> [offset] [beep] [s=<silence>]
    
    silence = stop after N seconds of silence (natural end of speech)
    timeout = absolute max recording time in ms
    """
    wav_file = rec_path + ".wav"
    
    # Clean up old file
    if os.path.exists(wav_file):
        os.remove(wav_file)

    # KEY: s=2 means "stop after 2 seconds of silence" - natural conversation flow
    # beep plays a beep before recording
    # 15000ms = 15 second max (won't reach if user stops talking)
    result = agi(f'RECORD FILE {rec_path} wav "#" 15000 0 BEEP s={max_silence_sec}')
    log(f"RECORD result: {result}")

    # Wait for the file to stabilize on disk
    waited = 0.0
    while waited < 8.0:
        if os.path.exists(wav_file):
            s1 = os.path.getsize(wav_file)
            if s1 > 1000:
                time.sleep(0.3)
                s2 = os.path.getsize(wav_file)
                if s1 == s2:
                    log(f"Recording stable at {s2} bytes")
                    return True, wav_file
        time.sleep(0.3)
        waited += 0.3

    exists = os.path.exists(wav_file)
    size = os.path.getsize(wav_file) if exists else 0
    log(f"Recording wait ended. exists={exists}, size={size}")
    return exists and size > 1000, wav_file

def is_silence(wav_file):
    """
    Check if recording is silence/noise (no real speech).
    Uses RMS energy of the audio samples.
    Threshold 300 filters out line noise and breathing but catches speech.
    """
    try:
        size = os.path.getsize(wav_file)
        log(f"Recording size: {size} bytes")

        # Too small = definitely silence  
        if size < 8000:
            log("File too small — treating as silence")
            return True

        with open(wav_file, 'rb') as f:
            # Skip WAV header (44 bytes) and read samples
            f.seek(44)
            # Read ~0.5 seconds of audio at 8kHz 16-bit = 8000 samples/sec
            data = f.read(32000)

        if len(data) < 200:
            return True

        import struct
        num_samples = len(data) // 2
        samples = struct.unpack(f'<{num_samples}h', data[:num_samples * 2])
        rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
        log(f"Audio RMS energy: {rms:.1f}")

        # 300 is a good threshold:
        # - Silence/noise: RMS < 100
        # - Breathing/ambient: RMS 100-300  
        # - Speech: RMS > 300
        if rms < 300:
            log("Low energy — silence/noise")
            return True

        return False

    except Exception as e:
        log(f"Silence check error: {e}")
        # If we can't check, assume it has audio if file is big enough
        return os.path.getsize(wav_file) < 8000

def cleanup_old_files():
    """Remove old TTS and recording files"""
    try:
        import glob
        # Clean TTS files older than 10 minutes
        for pattern in ["/var/lib/asterisk/sounds/lucy/reply_*.wav"]:
            for f in glob.glob(pattern):
                try:
                    if time.time() - os.path.getmtime(f) > 600:
                        os.remove(f)
                except:
                    pass
        # Clean old recordings
        for f in glob.glob("/tmp/lucy_*.wav"):
            try:
                if time.time() - os.path.getmtime(f) > 300:
                    os.remove(f)
            except:
                pass
    except:
        pass

# ═══════════════════════════════════════════════════════════
#  MAIN CALL HANDLER
# ═══════════════════════════════════════════════════════════
try:
    log("========== NEW CALL ==========")
    cleanup_old_files()

    # ── Read AGI environment variables ──
    env = {}
    while True:
        raw = sys.stdin.readline()
        s = raw.rstrip('\r\n')
        log(f"ENV: [{s}]")
        if s.strip() == "":
            drain_pipe()
            break
        if ":" in s:
            k, v = s.split(":", 1)
            env[k.strip()] = v.strip()

    caller = env.get("agi_callerid", "unknown")
    channel = env.get("agi_channel", "?")
    log(f"Caller: {caller} | Channel: {channel}")

    # Small delay to let channel fully establish
    time.sleep(0.8)

    reset_conversation()

    # ── Welcome Message ──
    welcome_text = (
        "Hello! I am Lucy, your Subharti Hospital assistant. "
        "How can I help you today?"
    )
    result = say(welcome_text)
    log(f"Welcome result: {result}")

    # ── Main Conversation Loop ──
    silence_count = 0
    max_silences = 3

    for turn in range(15):
        log(f"=== TURN {turn + 1} ===")

        ts = int(time.time())
        rec_path = f"{REC_DIR}/lucy_{ts}_{turn}"
        wav_file = rec_path + ".wav"

        # Record caller's speech (auto-stops after 2 sec silence)
        found, wav_file = record_audio(rec_path, max_silence_sec=2, max_duration_sec=15)
        log(f"Recording found: {found} | {wav_file}")

        if not found:
            silence_count += 1
            log(f"No recording (silence_count={silence_count})")
            if silence_count >= max_silences:
                say("I haven't heard from you for a while. Thank you for calling Subharti Hospital. Goodbye!")
                break
            say("I didn't hear you. Please speak after the beep.")
            continue

        # Check for silence/noise
        if is_silence(wav_file):
            silence_count += 1
            log(f"Silence detected (silence_count={silence_count})")
            if os.path.exists(wav_file):
                os.remove(wav_file)
            if silence_count >= max_silences:
                say("I haven't heard from you. Thank you for calling. Goodbye!")
                break
            say("I didn't catch that. Please speak clearly.")
            continue

        # Reset silence counter - we got real audio
        silence_count = 0

        # ── Transcribe ──
        size = os.path.getsize(wav_file)
        log(f"Speech detected! Transcribing {size} bytes...")

        try:
            text = transcribe_audio_groq(wav_file)
            log(f"STT: [{text}]")
        except Exception as e:
            log(f"STT error: {e}")
            text = ""
        finally:
            if os.path.exists(wav_file):
                os.remove(wav_file)

        if not text.strip():
            say("Sorry, I could not understand. Please try again.")
            continue

        # ── Check for goodbye ──
        goodbye_words = ["bye", "goodbye", "quit", "exit", "thank you", "thanks",
                        "alvida", "dhanyawad", "shukriya", "बाय", "अलविदा", "धन्यवाद"]
        if any(w in text.lower() for w in goodbye_words):
            say("Thank you for calling Subharti Hospital. Have a healthy day. Goodbye!")
            time.sleep(1.5)
            break

        # ── Get AI Response ──
        try:
            reply = get_groq_response(text, caller_number=caller)
            log(f"AI: [{reply}]")
        except Exception:
            log(traceback.format_exc())
            reply = "I'm sorry, I'm having trouble right now. Please call our helpline at 09639010313."

        # ── Speak Response ──
        say(reply)

    # ── Hang up ──
    agi("HANGUP", read_response=False)
    log("=== CALL ENDED ===")

except BrokenPipeError:
    log("=== CALL DROPPED (BrokenPipe) ===")
except Exception as e:
    log(f"FATAL ERROR: {e}\n{traceback.format_exc()}")
    try:
        agi_send("HANGUP")
    except:
        pass
