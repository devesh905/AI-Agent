import subprocess
import os
import time

OUTPUT_DIR = "/var/lib/asterisk/sounds/en"
OUTPUT_FILE_BASE = "ai_reply"

def text_to_speech(text):
    timestamp = int(time.time())
    wav_file = f"/tmp/ai_reply_{timestamp}.wav"
    output_file = f"{OUTPUT_DIR}/{OUTPUT_FILE_BASE}_{timestamp}"

    try:
        subprocess.run([
            "/usr/bin/espeak-ng",
            "-v", "en-us",
            "-s", "150",
            "-p", "50",
            "-w", wav_file,
            text
        ], check=True)

        subprocess.run([
            "/usr/bin/sox",
            wav_file,
            "-r", "8000",
            "-c", "1",
            "-t", "ul",
            output_file + ".ulaw"
        ], check=True)

        os.remove(wav_file)
        return output_file

    except Exception:
        return None
