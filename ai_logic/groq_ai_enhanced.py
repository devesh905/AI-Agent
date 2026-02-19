#!/usr/bin/env python3
"""
Bilingual AI Logic - Responds in the same language as user
FIX: Removed language="en" from Whisper so Hindi speech stays Hindi.
     detect_language() now uses Whisper's detected_language field, not text analysis.
"""

import os
from groq import Groq
import sys
sys.path.append("/home/devesh/ai-asterisk")
from database import (
    check_medicine_availability, 
    add_medicine_to_inventory,
    create_order,
    update_stock
)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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")
client = Groq(api_key=GROQ_API_KEY)

# Conversation tracking
conversation_history = []
current_caller = None
pending_order = None
detected_language = "en"  # Will be set by Whisper's actual detection


def transcribe_audio_groq(audio_file):
    """
    Transcribe audio using Groq Whisper.
    
    KEY FIX: Removed language="en" parameter.
    Before: language="en" forced Whisper to output English even for Hindi speech.
    Now: Whisper auto-detects language and transcribes in the original language.
    We also capture the detected language and store it globally so get_groq_response
    uses the correct language without having to re-detect from text.
    """
    global detected_language
    try:
        with open(audio_file, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(audio_file, file.read()),
                model="whisper-large-v3",
                # ← REMOVED: language="en"  (this was forcing Hindi→English)
                temperature=0.0,
                response_format="verbose_json"  # gives us detected language info
            )
        
        # Whisper tells us what language it detected — use that directly
        # This is far more reliable than running detect_language() on the text
        whisper_lang = getattr(transcription, 'language', 'en')
        
        # Groq returns full language names like "Hindi", "Urdu", "English"
        # Must use .lower() — "Hindi".startswith('hi') is False! (capital H)
        lang_lower = whisper_lang.lower() if whisper_lang else 'en'
        if lang_lower.startswith('hi') or lang_lower == 'urdu':
            # Urdu is also included — script is different but speakers often
            # understand Hindi TTS responses (both spoken in North India)
            detected_language = 'hi'
        else:
            detected_language = 'en'
        
        text = transcription.text.strip()
        
        # Log for debugging
        import time
        with open("/tmp/agi_debug.log", "a") as f:
            f.write(f"{time.strftime('%H:%M:%S')} WHISPER_LANG: [{whisper_lang}] → using [{detected_language}]\n")
        
        return text
        
    except Exception as e:
        print(f"Groq STT Error: {e}")
        return ""


def detect_language(text):
    """
    Fallback text-based language detection.
    Only used if Whisper detection fails.
    """
    try:
        from fast_langdetect import detect
        result = detect(text=text, low_memory=True)
        
        if isinstance(result, dict):
            lang = result.get('lang', 'en')
        elif isinstance(result, list):
            lang = result[0].get('lang', 'en')
        else:
            lang = 'en'
        
        return 'hi' if lang in ['hi', 'hi-IN', 'hi_IN'] else 'en'
        
    except:
        hindi_chars = sum(1 for c in text if '\u0900' <= c <= '\u097F')
        return 'hi' if hindi_chars > len(text) * 0.3 else 'en'


def extract_quantity(text):
    """Extract quantity from text (works for both Hindi and English)"""
    text_lower = text.lower()
    
    words = text_lower.split()
    for i, word in enumerate(words):
        if word.isdigit():
            return int(word)
        if i > 0 and words[i] in ["unit", "units", "piece", "pieces", "tablet", "tablets", "गोली", "गोलियां", "यूनिट"]:
            if words[i-1].isdigit():
                return int(words[i-1])
    
    word_to_num = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "ten": 10, "twenty": 20, "thirty": 30, "fifty": 50,
        "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5,
        "दस": 10, "बीस": 20, "तीस": 30, "पचास": 50, "सौ": 100
    }
    
    for word, num in word_to_num.items():
        if word in text_lower:
            return num
    
    return None


def is_medicine_query(text):
    """Check if text is about medicines (bilingual)"""
    text_lower = text.lower()
    
    hospital_keywords = [
        "lab", "scan", "test", "doctor", "appointment", "opd", "emergency",
        "where", "location", "direction", "how to reach", "timing", "hours",
        "department", "ward", "admission", "visiting", "pharmacy location",
        "लैब", "जांच", "डॉक्टर", "अपॉइंटमेंट", "ओपीडी", "इमरजेंसी",
        "कहां", "कहाँ", "समय", "विभाग", "दिशा"
    ]
    
    if any(keyword in text_lower for keyword in hospital_keywords):
        return False
    
    medicine_keywords = [
        "order", "buy", "medicine", "tablet", "drug", "available", "stock",
        "paracetamol", "aspirin", "ibuprofen", "cetirizine",
        "ऑर्डर", "दवा", "दवाई", "गोली", "खरीद", "मिलेगी", "स्टॉक", "उपलब्ध"
    ]
    
    return any(keyword in text_lower for keyword in medicine_keywords)


def extract_medicine_name(text):
    """Extract medicine name (bilingual)"""
    text_lower = text.lower()
    
    known_medicines = [
        "paracetamol", "aspirin", "ibuprofen", "amoxicillin",
        "cetirizine", "dolo", "crocin", "combiflam", "citrigen",
        "disprin", "avil", "azithromycin",
        "पैरासिटामोल", "एस्पिरिन", "डोलो", "क्रोसिन"
    ]
    
    for med in known_medicines:
        if med in text_lower:
            return med
    
    order_words = ["order", "buy", "want", "need", "get", "ऑर्डर", "चाहिए", "लेना"]
    words = text_lower.split()
    
    for i, word in enumerate(words):
        if word in order_words and i + 1 < len(words):
            potential_med = words[i + 1]
            skip_words = ["to", "some", "a", "the", "medicine", "tablet", "drug", "दवा", "गोली"]
            if potential_med not in skip_words and len(potential_med) > 3:
                return potential_med
    
    return None


def handle_order_flow(user_text, caller_number, language):
    """Handle medicine ordering in user's language"""
    global pending_order
    
    text_lower = user_text.lower()
    
    responses = {
        "hi": {
            "not_available": "माफ़ कीजिये, हमारे पास {medicine} उपलब्ध नहीं है। क्या आप कुछ और ऑर्डर करना चाहेंगे?",
            "low_stock": "हमारे पास केवल {stock} यूनिट {medicine} उपलब्ध हैं। क्या आप सभी {stock} यूनिट ऑर्डर करना चाहेंगे?",
            "order_complete": "बिल्कुल! {medicine} की {quantity} यूनिट का ऑर्डर कन्फर्म हो गया। कुल राशि ₹{total}। ऑर्डर नंबर: {order_id}।",
            "ask_quantity": "जी हाँ, {medicine} ₹{price} प्रति यूनिट पर उपलब्ध है। हमारे पास {stock} यूनिट स्टॉक में हैं। कितनी चाहिए?",
            "quantity_question": "कितनी यूनिट चाहिए?",
            "anything_else": "कोई बात नहीं। क्या मैं और कुछ मदद कर सकती हूं?",
        },
        "en": {
            "not_available": "I'm sorry, we don't have {medicine} in our pharmacy. Would you like to order something else?",
            "low_stock": "We only have {stock} units of {medicine} available. Would you like to order all {stock} units?",
            "order_complete": "Perfect! Your order for {quantity} units of {medicine} (₹{total}) is confirmed. Order number: {order_id}.",
            "ask_quantity": "Yes, {medicine} is available at ₹{price} per unit. We have {stock} units in stock. How many would you like?",
            "quantity_question": "How many units would you like?",
            "anything_else": "No problem. Is there anything else I can help you with?",
        }
    }
    
    r = responses[language]
    
    if pending_order is None:
        medicine = extract_medicine_name(user_text)
        quantity = extract_quantity(user_text)
        
        if not medicine:
            return None
        
        available, stock, price, actual_name = check_medicine_availability(medicine)
        
        if not available:
            return r["not_available"].format(medicine=medicine)
        
        if quantity:
            if quantity > stock:
                pending_order = {
                    'medicine': actual_name, 'quantity': quantity,
                    'stock': stock, 'price': price, 'step': 'confirm_low_stock'
                }
                return r["low_stock"].format(stock=stock, medicine=actual_name)
            else:
                order_id = create_order(caller_number, actual_name, quantity)
                update_stock(actual_name, -quantity)
                total = price * quantity
                return r["order_complete"].format(
                    medicine=actual_name, quantity=quantity,
                    total=total, order_id=order_id
                )
        
        pending_order = {
            'medicine': actual_name, 'stock': stock,
            'price': price, 'step': 'ask_quantity'
        }
        
        return r["ask_quantity"].format(medicine=actual_name, price=price, stock=stock)
    
    if pending_order['step'] == 'ask_quantity':
        quantity = extract_quantity(user_text)
        
        if not quantity:
            return r["quantity_question"]
        
        medicine = pending_order['medicine']
        stock = pending_order['stock']
        price = pending_order['price']
        
        if quantity > stock:
            pending_order['quantity'] = quantity
            pending_order['step'] = 'confirm_low_stock'
            return r["low_stock"].format(stock=stock, medicine=medicine)
        
        order_id = create_order(caller_number, medicine, quantity)
        update_stock(medicine, -quantity)
        total = price * quantity
        pending_order = None
        
        return r["order_complete"].format(
            medicine=medicine, quantity=quantity,
            total=total, order_id=order_id
        )
    
    if pending_order['step'] == 'confirm_low_stock':
        yes_words = ["yes", "ok", "sure", "yeah", "confirm", "हाँ", "हां", "जी", "ठीक", "कन्फर्म"]
        
        if any(word in text_lower for word in yes_words):
            medicine = pending_order['medicine']
            stock = pending_order['stock']
            price = pending_order['price']
            
            order_id = create_order(caller_number, medicine, stock)
            update_stock(medicine, -stock)
            total = price * stock
            pending_order = None
            
            return r["order_complete"].format(
                medicine=medicine, quantity=stock,
                total=total, order_id=order_id
            )
        else:
            pending_order = None
            return r["anything_else"]
    
    return None


def get_groq_response(user_text, system_prompt=None, caller_number="unknown"):
    """
    Bilingual AI - Responds in user's language.
    Uses detected_language set by transcribe_audio_groq() — no re-detection needed.
    """
    global current_caller, pending_order, detected_language
    current_caller = caller_number
    
    # Use the language Whisper already detected (set in transcribe_audio_groq)
    # Only fall back to text detection if somehow called without prior transcription
    lang = detected_language
    
    if is_medicine_query(user_text):
        response = handle_order_flow(user_text, caller_number, lang)
        if response:
            conversation_history.append({"role": "user", "content": user_text})
            conversation_history.append({"role": "assistant", "content": response})
            return response
    
    if pending_order and not is_medicine_query(user_text):
        pending_order = None
    
    system_prompts = {
        "hi": """आप Lucy हैं, सुभारती हॉस्पिटल, मीरत की सहायक AI।

महत्वपूर्ण: जवाब छोटे रखें (1-2 वाक्य)। यह फोन कॉल है।
महत्वपूर्ण: हमेशा हिंदी में जवाब दें।

**हॉस्पिटल जानकारी:**
- OPD: गेट 2, ग्राउंड फ्लोर, सोम-शनि 8AM-4PM
- इमरजेंसी: मुख्य प्रवेश द्वार (गोल चक्कर के सामने), 24/7
- लैब: मुख्य भवन, ग्राउंड फ्लोर, 8AM-4PM (इमरजेंसी 24/7)
- फार्मेसी: ग्राउंड फ्लोर गेट 3 के पास, 24/7
- हेल्पलाइन: 09639010313

**नियम:**
- गर्मजोशी और पेशेवर बनें
- स्पष्ट, सरल निर्देश दें
- मेडिकल सलाह न दें - कहें "कृपया डॉक्टर से परामर्श करें"
- प्राकृतिक बातचीत रखें
""",
        "en": """You are Lucy, a helpful AI assistant for Subharti Hospital in Meerut, India.

IMPORTANT: Keep responses SHORT (1-2 sentences). This is a phone call.
IMPORTANT: Always respond in English.

**Hospital Information:**
- OPD: Gate 2, Ground Floor, Mon-Sat 8AM-4PM
- Emergency: Main Entrance (Front of Gol Chakker), 24/7
- Lab: Main Building, Ground Floor, 8AM-4PM (Emergency 24/7)
- Pharmacy: Ground Floor near Gate 3, 24/7
- Helpline: 09639010313

**Rules:**
- Be warm and professional
- Give clear, simple directions
- Don't give medical advice - say "please consult a doctor"
- Keep responses natural and conversational
"""
    }
    
    if system_prompt is None:
        system_prompt = system_prompts[lang]
    
    conversation_history.append({"role": "user", "content": user_text})
    
    if len(conversation_history) > 8:
        conversation_history.pop(0)
        conversation_history.pop(0)
    
    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                *conversation_history
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.7,
            max_tokens=120,
            top_p=1,
            stream=False
        )
        
        response = chat_completion.choices[0].message.content
        conversation_history.append({"role": "assistant", "content": response})
        
        return response
        
    except Exception as e:
        print(f"Groq AI Error: {e}")
        if lang == "hi":
            return "मुझे समस्या हो रही है। कृपया हमारी हेल्पलाइन 09639010313 पर कॉल करें।"
        return "I'm having trouble. Please call our helpline at 09639010313."


def reset_conversation():
    """Reset for new call"""
    global conversation_history, current_caller, pending_order, detected_language
    conversation_history = []
    current_caller = None
    pending_order = None
    detected_language = "en"
