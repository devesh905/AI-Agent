import subprocess
import time
import os

PIPER_BIN = "/home/devesh/ai-asterisk/venv/bin/piper"
VOICE = "/home/devesh/ai-asterisk/en_US-lessac-medium.onnx"
OUTPUT_DIR = "/var/lib/asterisk/sounds/en"

def text_to_speech(text):
    ts = int(time.time())
    temp_wav = f"/tmp/piper_temp_{ts}.wav"
    final_wav = f"{OUTPUT_DIR}/ai_reply_{ts}.wav"
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Step 1: Generate audio with Piper
    cmd = [PIPER_BIN, "--model", VOICE, "--output_file", temp_wav]
    
    proc = subprocess.Popen(
        cmd, 
        stdin=subprocess.PIPE, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.PIPE, 
        text=True
    )
    
    stdout, stderr = proc.communicate(input=text + "\n")
    
    if proc.returncode != 0:
        raise RuntimeError(f"Piper failed: {stderr}")
    
    if not os.path.exists(temp_wav):
        raise RuntimeError(f"Piper output not created: {temp_wav}")
    
    # Step 2: Convert to Asterisk format (8000 Hz, 16-bit, mono)
    # Using sox or ffmpeg
    try:
        # Try sox first (faster)
        subprocess.run([
            "sox",
            temp_wav,
            "-r", "8000",  # Sample rate 8000 Hz
            "-c", "1",     # Mono
            "-b", "16",    # 16-bit
            final_wav
        ], check=True, stderr=subprocess.PIPE)
    except (FileNotFoundError, subprocess.CalledProcessError):
        # Fallback to ffmpeg
        subprocess.run([
            "ffmpeg",
            "-i", temp_wav,
            "-ar", "8000",
            "-ac", "1",
            "-y",
            final_wav
        ], check=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    
    # Clean up temp file
    os.remove(temp_wav)
    
    if not os.path.exists(final_wav):
        raise RuntimeError(f"Converted file not created: {final_wav}")
    
    return final_wav.replace(".wav", "")