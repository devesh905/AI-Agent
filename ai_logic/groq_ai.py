# File: /home/devesh/ai-asterisk/ai_logic/groq_ai.py

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

    try:
        with open(audio_file, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(audio_file, file.read()),
                model="whisper-large-v3",
                language="en",  # Change to "hi" for Hindi, or remove for auto-detect
                temperature=0.0,
                response_format="json"
            )
        return transcription.text.strip()
    except Exception as e:
        print(f"Groq STT Error: {e}")
        return ""


def get_groq_response(user_text, system_prompt=None):
    
    # Default system prompt for banking assistant
    if system_prompt is None:
        system_prompt = """You are a helpful banking assistant for a phone call system.
Rules:
- Keep responses SHORT (1-2 sentences max)
- Be friendly and professional
- Speak naturally (this will be converted to speech)
- Handle: balance inquiries, transactions, account info
- If asked something you don't know, say "Let me transfer you to a representative"
- Don't use special characters or formatting
"""

    # Add user message to history
    conversation_history.append({"role": "user", "content": user_text})
    
    # Keep only last 10 messages (to stay within token limits)
    if len(conversation_history) > 10:
        conversation_history.pop(0)
        conversation_history.pop(0)  # Remove user + assistant pair
    
    try:
        # Call Groq API
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                *conversation_history
            ],
            model="llama-3.3-70b-versatile",  # Fast and smart
            temperature=0.7,
            max_tokens=150,  # Keep responses short for TTS
            top_p=1,
            stream=False
        )
        
        response = chat_completion.choices[0].message.content
        
        # Add assistant response to history
        conversation_history.append({"role": "assistant", "content": response})
        
        return response
        
    except Exception as e:
        print(f"Groq AI Error: {e}")
        return "I'm having trouble processing that. Please try again."


def reset_conversation():
    """Reset conversation history for new call"""
    global conversation_history
    conversation_history = []


