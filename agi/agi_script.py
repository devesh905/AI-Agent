#!/home/devesh/ai-asterisk/venv/bin/python3
"""
Enhanced AGI Script with Database Integration
FULLY BACKWARDS COMPATIBLE - Won't break existing functionality
"""

import sys, os, time, traceback

BASE = "/home/devesh/ai-asterisk"
RECORD_DIR = "/var/lib/asterisk/sounds/recordings"
LOG = "/tmp/agi_debug.log"

sys.path.append(BASE)

# Import enhanced AI with database support
from ai_logic.groq_ai_enhanced import transcribe_audio_groq, get_groq_response, reset_conversation
from tts.tts_piper import text_to_speech

def log(m):
    with open(LOG, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {m}\n")

def agi_read():
    l = sys.stdin.readline().strip()
    log("RECV: " + l)
    return l

def agi(cmd):
    sys.stdout.write(cmd + "\n")
    sys.stdout.flush()
    log("SENT: " + cmd)
    return agi_read()

try:
    log("========== NEW CALL STARTED ==========")
    
    # Read AGI environment
    env = {}
    while True:
        line = agi_read()
        if not line:
            break
        if ':' in line:
            key, val = line.split(':', 1)
            env[key.strip()] = val.strip()
    
    log(f"AGI Environment loaded: {len(env)} vars")
    
    # Extract caller number for database orders
    caller_number = env.get('agi_callerid', 'unknown')
    log(f"Caller Number: {caller_number}")
    
    # Answer the call
    result = agi("ANSWER")
    log(f"Answer result: {result}")
    time.sleep(0.5)
    
    # Reset conversation for new call
    reset_conversation()
    log("Conversation reset")
    
    # Play welcome message
    welcome = "Hello! I'm Lucy, your Subharti Hospital assistant. I can help with hospital info and medicine orders. How can I help you today?"
    log(f"Generating welcome TTS: {welcome}")
    
    try:
        welcome_file = text_to_speech(welcome)
        log(f"Welcome file created: {welcome_file}")
        result = agi(f'STREAM FILE {welcome_file} ""')
        log(f"Welcome playback result: {result}")
    except Exception as e:
        log(f"ERROR in welcome TTS: {e}")
        result = agi('STREAM FILE hello-world ""')
        log(f"Fallback playback result: {result}")
    
    time.sleep(0.3)

    MAX_TURNS = 10

    for turn in range(MAX_TURNS):
        log(f"========== TURN {turn+1}/{MAX_TURNS} ==========")

        record_file = f"{RECORD_DIR}/input_{int(time.time())}_{turn}"
        audio_file = record_file + ".wav"

        if os.path.exists(audio_file):
            os.remove(audio_file)
            log(f"Deleted old recording: {audio_file}")

        # Play beep
        result = agi('STREAM FILE beep ""')
        log(f"Beep result: {result}")
        time.sleep(0.1)

        # Record with 2 second silence detection
        log(f"Starting recording to: {record_file}")
        result = agi(f'RECORD FILE {record_file} wav "#" 10000 s=2 BEEP')
        log(f"Recording result: {result}")
        
        if "result=-1" in result or "writefile" in result:
            log("ERROR: Recording failed - breaking loop")
            break

        time.sleep(0.5)

        if not os.path.exists(audio_file):
            log(f"ERROR: File not found: {audio_file}")
            break

        file_size = os.path.getsize(audio_file)
        log(f"Recording created: {file_size} bytes")
        
        if file_size < 5000:
            log("Recording too short - probably silence")
            reply = "I didn't hear you. Please speak after the beep."
            try:
                out = text_to_speech(reply)
                agi(f'STREAM FILE {out} ""')
            except Exception as e:
                log(f"ERROR in silence TTS: {e}")
            
            try:
                os.remove(audio_file)
            except:
                pass
            
            continue

        # Transcribe using Groq
        log("Starting transcription...")
        start = time.time()
        try:
            text = transcribe_audio_groq(audio_file)
            stt_time = time.time() - start
            log(f"STT completed in {stt_time:.2f}s: '{text}'")
        except Exception as e:
            log(f"ERROR in transcription: {e}")
            log(traceback.format_exc())
            text = ""

        # Delete recording after transcription
        try:
            os.remove(audio_file)
            log("Recording deleted")
        except Exception as e:
            log(f"Could not delete recording: {e}")

        if not text.strip():
            log("Empty transcription received")
            reply = "I couldn't understand that. Please try again."
            try:
                out = text_to_speech(reply)
                agi(f'STREAM FILE {out} ""')
            except Exception as e:
                log(f"ERROR in empty transcription TTS: {e}")
            continue

        # Check for goodbye
        goodbye_words = ["bye", "goodbye", "exit", "quit", "thank you bye", "that's all"]
        if any(word in text.lower() for word in goodbye_words):
            if "thank" in text.lower() and not any(x in text.lower() for x in ["bye", "all", "exit"]):
                log("Just 'thank you' - continuing conversation")
                pass
            else:
                log("Goodbye detected - ending call")
                reply = "Thank you for calling. Have a great day!"
                try:
                    out = text_to_speech(reply)
                    agi(f'STREAM FILE {out} ""')
                except Exception as e:
                    log(f"ERROR in goodbye TTS: {e}")
                break

        # Get AI response with database support
        log("Getting AI response with database integration...")
        start = time.time()
        try:
            # PASS CALLER NUMBER for database operations
            reply = get_groq_response(text, caller_number=caller_number)
            ai_time = time.time() - start
            log(f"AI response in {ai_time:.2f}s: '{reply}'")
        except Exception as e:
            log(f"ERROR in AI response: {e}")
            log(traceback.format_exc())
            reply = "I'm having trouble right now. Let me transfer you to someone who can help."

        # Speak response
        log("Generating response TTS...")
        try:
            out = text_to_speech(reply)
            log(f"TTS file created: {out}")
            result = agi(f'STREAM FILE {out} ""')
            log(f"Response playback result: {result}")
        except Exception as e:
            log(f"ERROR in response TTS: {e}")
            log(traceback.format_exc())

        time.sleep(0.2)

    log("Conversation loop ended - hanging up")
    agi("HANGUP")
    log("========== CALL ENDED ==========")

except Exception as e:
    log("========== FATAL EXCEPTION ==========")
    log(f"Exception: {str(e)}")
    log(traceback.format_exc())
    try:
        agi("HANGUP")
    except:
        pass
