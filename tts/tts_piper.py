#!/usr/bin/env python3
"""
Lucy TTS - piper-tts compatible
Output: slin WAV (8kHz, 16-bit PCM mono) — Asterisk STREAM FILE compatible
FIX: Changed from pcm_mulaw (ulaw) to pcm_s16le (slin) which Asterisk reads reliably
"""

import time, os, wave, subprocess

# Asterisk reads from this base path — use 'en' subdir for BOTH languages
# because we'll pass full path anyway
OUTPUT_DIR_BASE = "/var/lib/asterisk/sounds/lucy"
DEFAULT_LANGUAGE = "hi"

VOICES = {
    "hi": {
        "model":  "/home/devesh/ai-asterisk/hi_IN-priyamvada-medium.onnx",
        "config": "/home/devesh/ai-asterisk/hi_IN-priyamvada-medium.onnx.json",
        "length_scale": 0.95,
    },
    "en": {
        "model":  "/home/devesh/ai-asterisk/en_US-lessac-medium.onnx",
        "config": "/home/devesh/ai-asterisk/en_US-lessac-medium.onnx.json",
        "length_scale": 1.0,
    }
}

_voice_cache = {}

def detect_language(text):
    try:
        from fast_langdetect import detect
        result = detect(text=text, low_memory=True)
        lang = result.get('lang', 'en') if isinstance(result, dict) else (result[0].get('lang', 'en') if result else 'en')
        return 'hi' if lang in ['hi', 'hi-IN', 'hi_IN'] else 'en'
    except Exception:
        # Fallback: check for Devanagari Unicode range
        hindi_chars = sum(1 for c in text if '\u0900' <= c <= '\u097F')
        return 'hi' if hindi_chars > len(text) * 0.2 else 'en'

def get_voice(language):
    if language not in _voice_cache:
        from piper import PiperVoice
        cfg = VOICES[language]
        config_path = cfg["config"] if os.path.exists(cfg["config"]) else None
        voice = PiperVoice.load(cfg["model"], config_path=config_path)
        _voice_cache[language] = voice
    return _voice_cache[language]

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    try:
        os.chmod(path, 0o777)
    except:
        pass
    try:
        subprocess.run(["sudo", "chown", "asterisk:asterisk", path], capture_output=True)
        subprocess.run(["sudo", "chmod", "777", path], capture_output=True)
    except:
        pass

def text_to_speech(text, force_language=None):
    """
    Generate TTS audio for Asterisk.
    Returns: absolute path WITHOUT .wav extension (for STREAM FILE command)
    
    KEY FIX: Output is now slin (pcm_s16le, 8kHz, mono) not ulaw.
    Asterisk's STREAM FILE handles slin WAV natively and reliably.
    """
    ts = int(time.time())
    
    language = force_language if (force_language and force_language in VOICES) else detect_language(text)
    if language not in VOICES:
        language = DEFAULT_LANGUAGE
    
    # Fallback to other language if model missing
    if not os.path.exists(VOICES[language]["model"]):
        other = "en" if language == "hi" else "hi"
        if os.path.exists(VOICES[other]["model"]):
            language = other
        else:
            raise RuntimeError("No voice model found for either language")

    ensure_dir(OUTPUT_DIR_BASE)

    temp_wav  = f"/tmp/piper_native_{ts}.wav"
    # Store in a flat directory under sounds/lucy/ - no language subdir needed
    final_wav = f"{OUTPUT_DIR_BASE}/reply_{ts}.wav"

    # ── Step 1: Generate audio with Piper (native sample rate, usually 22050Hz) ──
    voice = get_voice(language)
    cfg   = VOICES[language]

    try:
        from piper import SynthesisConfig
        syn_cfg = SynthesisConfig(length_scale=cfg["length_scale"])
        with wave.open(temp_wav, "wb") as wf:
            voice.synthesize_wav(text, wf, syn_config=syn_cfg)
    except (ImportError, AttributeError, TypeError):
        try:
            with wave.open(temp_wav, "wb") as wf:
                voice.synthesize(text, wf)
        except Exception:
            with wave.open(temp_wav, "wb") as wf:
                voice.synthesize_wav(text, wf)

    if not os.path.exists(temp_wav) or os.path.getsize(temp_wav) < 100:
        raise RuntimeError("Piper produced no audio")

    # ── Step 2: Convert to slin WAV (8kHz, 16-bit PCM, mono) ──
    # THIS IS THE CRITICAL FIX:
    # Old code used: -acodec pcm_mulaw  → ulaw format → Asterisk result=-1
    # New code uses: -acodec pcm_s16le  → slin format → Asterisk plays correctly
    r = subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", temp_wav,
        "-ar", "8000",       # 8kHz sample rate (Asterisk native)
        "-ac", "1",          # Mono
        "-acodec", "pcm_s16le",  # 16-bit PCM = slin = what Asterisk loves
        final_wav
    ], capture_output=True, text=True)

    if os.path.exists(temp_wav):
        os.remove(temp_wav)

    if r.returncode != 0 or not os.path.exists(final_wav):
        raise RuntimeError(f"FFmpeg failed: {r.stderr}")

    # Set permissions so Asterisk (running as asterisk user) can read it
    try:
        os.chmod(final_wav, 0o644)
    except:
        pass
    try:
        subprocess.run(["sudo", "chown", "asterisk:asterisk", final_wav], capture_output=True)
    except:
        pass

    # Flush to disk
    try:
        with open(final_wav, 'rb') as f:
            os.fsync(f.fileno())
    except:
        pass

    # Return path WITHOUT .wav extension (for AGI STREAM FILE command)
    return final_wav.replace(".wav", "")


if __name__ == "__main__":
    # Test both languages
    subprocess.run([
        "sudo", "mkdir", "-p",
        "/var/lib/asterisk/sounds/lucy"
    ], capture_output=True)
    subprocess.run([
        "sudo", "chmod", "777",
        "/var/lib/asterisk/sounds/lucy"
    ], capture_output=True)

    print("=" * 50)
    print("Testing TTS (slin format)...")
    for lang, text in [
        ("en", "Hello! I am Lucy, your Subharti Hospital assistant. Please speak after the beep."),
        ("hi", "नमस्ते! मैं लूसी हूं, सुभारती हॉस्पिटल की सहायक।"),
    ]:
        print(f"\nTesting [{lang}]...")
        try:
            path = text_to_speech(text, force_language=lang)
            wav = path + ".wav"
            size = os.path.getsize(wav)
            r = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_streams", "-of", "json", wav],
                capture_output=True, text=True
            )
            print(f"  ✓ {size} bytes at {wav}")
            if "pcm_s16le" in r.stdout:
                print(f"  ✓ FORMAT CORRECT! (slin pcm_s16le 8kHz mono)")
            else:
                print(f"  ⚠ ffprobe: {r.stdout[:300]}")
        except Exception as e:
            print(f"  ✗ {e}")
            import traceback; traceback.print_exc()
