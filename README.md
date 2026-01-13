An intelligent voice call system powered by AI, built with Asterisk, Groq API, and Piper TTS.

## Features ✨

- **Ultra-fast Speech Recognition** - Groq Whisper API (0.2-0.4s)
- **Smart AI Responses** - LLaMA 3.3 70B conversational AI
- **Natural Voice** - Piper TTS (free, high-quality)
- **Real-time Conversations** - Auto voice detection, context-aware
- **Banking Assistant** - Account balance, transactions, support

## Tech Stack 🛠️

- **PBX**: Asterisk (VoIP/telephony)
- **STT**: Groq Whisper Large V3
- **AI**: Groq LLaMA 3.3 70B
- **TTS**: Piper (Mozilla TTS)
- **Language**: Python 3.12
- **OS**: Ubuntu 24.04

┌─────────────┐
│   Phone     │
│   Call      │
└──────┬──────┘
│
┌──────▼──────────┐
│   Asterisk      │
│   (PBX)         │
└──────┬──────────┘
│
┌──────▼──────────┐
│  AGI Script     │
│  (ai_call.py)   │
└──────┬──────────┘
│
┌──────▼──────────────────────────────────┐
│  AI Pipeline                             │
│  ┌────────┐  ┌──────┐  ┌──────────┐    │
│  │  STT   │─▶│  AI  │─▶│   TTS    │    │
│  │ Groq   │  │ Groq │  │  Piper   │    │
│  └────────┘  └──────┘  └──────────┘    │
└──────────────────────────────────────────┘
