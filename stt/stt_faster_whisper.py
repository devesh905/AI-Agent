import os
from faster_whisper import WhisperModel

# Model sizes: tiny, base, small, medium, large-v3
# tiny = fastest, least accurate
# base = good balance for phone calls
# small = better accuracy, still fast
MODEL_SIZE = "base"
MODEL = None

def get_model():
    """Load model once and reuse it"""
    global MODEL
    if MODEL is None:
        # Use CPU or GPU (cuda)
        # Set compute_type="int8" for CPU, "float16" for GPU
        MODEL = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
    return MODEL

def speech_to_text(audio_file):
    """
    Convert speech to text using Faster-Whisper (local)
    - No API key needed
    - No costs
    - Fast and accurate
    - Works with any sample rate
    """
    
    if not os.path.exists(audio_file):
        return ""
    
    try:
        model = get_model()
        
        # Transcribe
        segments, info = model.transcribe(
            audio_file,
            language="en",
            beam_size=5,
            vad_filter=True,  # Remove silence
            vad_parameters=dict(min_silence_duration_ms=500)
        )
        
        # Combine all segments
        text = " ".join([segment.text for segment in segments])
        
        return text.strip()
        
    except Exception as e:
        print(f"Faster-Whisper STT error: {e}")
        return ""
