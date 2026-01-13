#!/home/devesh/ai-asterisk/venv/bin/python3

import sys, os, time, traceback

BASE = "/home/devesh/ai-asterisk"
RECORD_DIR = "/var/lib/asterisk/sounds/recordings"
LOG = "/tmp/agi_debug.log"

sys.path.append(BASE)

from ai_logic.groq_ai import transcribe_audio_groq, get_groq_response, reset_conversation
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
    # Read AGI environment
    while agi_read():
        pass

    agi("ANSWER")
    time.sleep(0.5)
    
    # Reset conversation for new call
    reset_conversation()
    
    # Play welcome message
    welcome = "Hello! I'm your banking assistant. How can I help you today?"
    welcome_file = text_to_speech(welcome)
    agi(f'STREAM FILE {welcome_file} ""')
    time.sleep(0.3)

    MAX_TURNS = 10  # Increased for better conversation

    for turn in range(MAX_TURNS):
        log(f"---- TURN {turn+1} ----")

        # Use unique filename
        record_file = f"{RECORD_DIR}/input_{int(time.time())}_{turn}"
        audio_file = record_file + ".wav"

        # Delete old recording if exists
        if os.path.exists(audio_file):
            os.remove(audio_file)

        # Play beep
        agi('STREAM FILE beep ""')
        time.sleep(0.1)

        # Record with SHORTER timeout (5 seconds silence = stop)
        # This stops recording automatically when user stops speaking
        result = agi(f'RECORD FILE {record_file} wav "#" 5000 s=2 BEEP')
        
        # s=2 means: stop if 2 seconds of silence detected
        # This makes it MUCH faster!
        
        log(f"Recording result: {result}")
        
        # Check if recording failed
        if "result=-1" in result or "writefile" in result:
            log("ERROR: Recording failed")
            break

        # Wait for file
        time.sleep(0.3)

        # Check file exists
        if not os.path.exists(audio_file):
            log(f"ERROR: File not found: {audio_file}")
            break

        file_size = os.path.getsize(audio_file)
        log(f"Recording size: {file_size} bytes")
        
        # Check for silence (very small file)
        if file_size < 5000:  # Less than ~0.3 seconds
            log("Too short - probably silence")
            reply = "I didn't hear you. Please speak after the beep."
            out = text_to_speech(reply)
            agi(f'STREAM FILE {out} ""')
            
            # Delete tiny recording
            try:
                os.remove(audio_file)
            except:
                pass
            
            continue

        # Transcribe using Groq (FAST!)
        start = time.time()
        text = transcribe_audio_groq(audio_file)
        stt_time = time.time() - start
        
        log(f"STT ({stt_time:.2f}s): '{text}'")

        # Delete recording after transcription
        try:
            os.remove(audio_file)
        except:
            pass

        # Handle empty transcription
        if not text.strip():
            reply = "I couldn't understand that. Please try again."
            out = text_to_speech(reply)
            agi(f'STREAM FILE {out} ""')
            continue

        # Check for goodbye
        goodbye_words = ["bye", "goodbye", "exit", "quit", "thank you bye", "that's all"]
        if any(word in text.lower() for word in goodbye_words):
            # Check if it's just "thank you" (not goodbye)
            if "thank" in text.lower() and not any(x in text.lower() for x in ["bye", "all", "exit"]):
                pass  # Continue conversation
            else:
                reply = "Thank you for calling. Have a great day!"
                out = text_to_speech(reply)
                agi(f'STREAM FILE {out} ""')
                break

        # Get AI response using Groq (FAST!)
        start = time.time()
        reply = get_groq_response(text)
        ai_time = time.time() - start
        
        log(f"AI ({ai_time:.2f}s): '{reply}'")

        # Speak response
        out = text_to_speech(reply)
        agi(f'STREAM FILE {out} ""')

        time.sleep(0.2)

    agi("HANGUP")

except Exception as e:
    log("EXCEPTION: " + str(e))
    log(traceback.format_exc())
    try:
        agi("HANGUP")
    except:
        pass
