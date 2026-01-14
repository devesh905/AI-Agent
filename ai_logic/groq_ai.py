import os
from groq import Groq

# Get your free API key from: https://console.groq.com/keys
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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")

if not GROQ_API_KEY:
    raise ValueError("Please set GROQ_API_KEY environment variable")

client = Groq(api_key=GROQ_API_KEY)

# Conversation history (for context)
conversation_history = []

def transcribe_audio_groq(audio_file):
    """
    Transcribe audio using Groq Whisper
    Supports English and Hindi
    """
    try:
        with open(audio_file, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(audio_file, file.read()),
                model="whisper-large-v3",
                language="en",  # Change to None for auto-detect
                temperature=0.0,
                response_format="json"
            )
        return transcription.text.strip()
    except Exception as e:
        print(f"Groq STT Error: {e}")
        return ""


def get_groq_response(user_text, system_prompt=None):
    """
    Get AI response for Subharti Hospital assistant
    """
    
    # Default system prompt - SHORTER version
    if system_prompt is None:
        system_prompt = """You are a helpful assistant for Subharti Hospital in Meerut, India.

IMPORTANT: Keep responses SHORT (2-3 sentences maximum). This is a phone call.

Key Information:
- OPD: Gate 2, Ground Floor, Mon-Sat 8:00 AM to 4:00 PM
- Consultation fees vary by doctor and speciality. They usually range depending on the experience of the doctor and department.
- Emergency: Gate 1 (Main Entrance), 24/7
- Lab: Main Building, Ground Floor, 8AM-4PM (Emergency 24/7)
- The hospital has a NABL-accredited central laboratory providing a wide range of tests for hematology, biochemistry, microbiology, serology, pathology, and more with quality standards.
- Pharmacy: Ground Floor near Gate 3, 24/7
- 24×7 functional Operation Theatres
- ICU/CCU/HDU for critical patients
- Helpline: 09639010313
- Email: it.hospital@subharti.org

Imaging & Radiology:
-The hospital has advanced imaging including:
-3 Tesla MRI
-160 slice CT Scanner
-Ultrasound, Doppler
-Digital X-Ray
-Digital Mammography
- 
Rules:
- Be warm and professional
- Give clear, simple directions
- Don't give medical advice - say "please consult a doctor"
- If unsure, offer to transfer to reception
- Keep it conversational and natural
"""

    # Add user message to history
    conversation_history.append({"role": "user", "content": user_text})
    
    # Keep only last 6 messages (3 turns) to avoid token issues
    if len(conversation_history) > 6:
        conversation_history.pop(0)
        conversation_history.pop(0)
    
    try:
        # Call Groq API
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                *conversation_history
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.7,
            max_tokens=150,  # Keep responses short
            top_p=1,
            stream=False
        )
        
        response = chat_completion.choices[0].message.content
        
        # Add assistant response to history
        conversation_history.append({"role": "assistant", "content": response})
        
        return response
        
    except Exception as e:
        print(f"Groq AI Error: {e}")
        return "I'm having trouble processing that. Please call our helpline at 0121-2439056 for immediate assistance."


def reset_conversation():
    """Reset conversation history for new call"""
    global conversation_history
    conversation_history = []