import os
from openai import OpenAI

# Set your API key here or use environment variable
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "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")

def speech_to_text(audio_file):
    """
    Convert speech to text using OpenAI Whisper API
    This is much more accurate than Vosk and handles any sample rate
    """
    
    if not os.path.exists(audio_file):
        return ""
    
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        # Open the audio file
        with open(audio_file, "rb") as audio:
            # Whisper automatically handles any sample rate!
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio,
                language="en"  # Optional: specify language for better accuracy
            )
        
        return transcript.text.strip()
        
    except Exception as e:
        print(f"Whisper STT error: {e}")
        return ""
