import json
import wave
import subprocess
import os
from vosk import Model, KaldiRecognizer

MODEL_PATH = "/home/devesh/ai-asterisk/models/vosk-model-small-en-us-0.15"

def resample_audio(input_file, output_file, target_rate=16000):
    """Resample audio to target sample rate using sox"""
    try:
        subprocess.run([
            'sox', input_file, 
            '-r', str(target_rate),
            output_file
        ], check=True, capture_output=True, text=True)
        return output_file
    except subprocess.CalledProcessError:
        return None

def speech_to_text(audio_file):
    """Convert speech audio to text using Vosk"""
    
    if not os.path.exists(audio_file):
        return ""
    
    # Check sample rate
    wf = wave.open(audio_file, "rb")
    sample_rate = wf.getframerate()
    wf.close()
    
    # Resample if needed
    audio_to_process = audio_file
    resampled_file = None
    
    if sample_rate != 16000:
        resampled_file = audio_file.replace('.wav', '_16k.wav')
        result = resample_audio(audio_file, resampled_file, 16000)
        if result:
            audio_to_process = resampled_file
    
    # Process with Vosk
    try:
        wf = wave.open(audio_to_process, "rb")
        model = Model(MODEL_PATH)
        rec = KaldiRecognizer(model, wf.getframerate())

        text = ""
        
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                text += result.get("text", "") + " "

        final = json.loads(rec.FinalResult())
        text += final.get("text", "")
        wf.close()
        
        # Clean up resampled file
        if resampled_file and os.path.exists(resampled_file):
            os.remove(resampled_file)
        
        return text.strip()
        
    except Exception:
        if resampled_file and os.path.exists(resampled_file):
            os.remove(resampled_file)
        return ""
