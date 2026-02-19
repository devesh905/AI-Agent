#!/usr/bin/env python3
"""
Bilingual AI Logic - Lucy for Subharti Hospital
FIXES in this version:
  1. extract_medicine_name() now queries the DATABASE directly — no hardcoded list.
     "Liv 52", "OSR", "Betadine", any future medicine added to DB works automatically.
  2. Pending order safety — if user mentions a NEW medicine while order is pending,
     old pending order is cleared and new one starts. No more wrong medicine orders.
  3. is_medicine_query() now also queries DB for medicine name matches.
  4. Hindi medicine orders now go through DB flow (not just redirected to pharmacy).
  5. Language detection uses Whisper's detected language (capital H "Hindi" fixed).
"""

import os, re, time, sqlite3
from groq import Groq
import sys
sys.path.append("/home/devesh/ai-asterisk")
from database import (
    check_medicine_availability,
    add_medicine_to_inventory,
    create_order,
    update_stock,
    DB_PATH
)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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")
client = Groq(api_key=GROQ_API_KEY)
LOG_FILE = "/tmp/agi_debug.log"

conversation_history = []
current_caller = None
pending_order = None
detected_language = "en"


def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")


# ─────────────────────────────────────────────
#  DATABASE HELPERS
# ─────────────────────────────────────────────

def get_all_medicine_names():
    """Fetch all medicine names from DB — no hardcoding needed."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM medicines")
        names = [row[0] for row in cursor.fetchall()]
        conn.close()
        return names
    except Exception as e:
        log(f"DB fetch error: {e}")
        return []


def find_medicine_in_text(text):
    """
    Search DB medicine names inside the user's spoken text.
    Handles: exact match, multi-word partial, numeric+letter, and DB fuzzy.
    e.g. "live 52" -> "Liv 52", "citrazen" -> "Cetirizine", "osr" -> "OSR"
    """
    text_lower = text.lower()
    medicines = get_all_medicine_names()

    # Pass 1: exact substring
    for med in medicines:
        if med.lower() in text_lower:
            log(f"MEDICINE_MATCH (exact): '{med}'")
            return med

    # Pass 2: all tokens of multi-word name present in text
    for med in medicines:
        tokens = med.lower().split()
        if len(tokens) > 1 and all(t in text_lower for t in tokens):
            log(f"MEDICINE_MATCH (all-tokens): '{med}'")
            return med

    # Pass 3: numeric part + first-char letter match (handles "live 52" -> "Liv 52")
    for med in medicines:
        tokens = med.lower().split()
        med_numbers = [t for t in tokens if t.isdigit()]
        med_letters = [t for t in tokens if not t.isdigit()]
        if med_numbers:
            num_match = all(n in text_lower for n in med_numbers)
            letter_match = any(
                any(tw.startswith(ml[0]) for tw in text_lower.split())
                for ml in med_letters
            )
            if num_match and letter_match:
                log(f"MEDICINE_MATCH (num+letter): '{med}'")
                return med

    # Pass 4: DB LIKE fuzzy — handles typos like "citrazen" -> "Cetirizine"
    skip = {"want","order","need","some","tablet","tablets","medicine","drug",
            "have","what","price","many","available","tell","please","can","you",
            "दवा","गोली","ऑर्डर","चाहिए","लेना","मुझे","करनी","करना","बताओ","बताएं","कितनी"}
    words = [w for w in re.findall(r'[a-zA-Z0-9\u0900-\u097F]+', text_lower)
             if len(w) > 3 and w not in skip]
    for word in words:
        available, stock, price, actual_name = check_medicine_availability(word)
        if available and actual_name:
            log(f"MEDICINE_MATCH (db-fuzzy '{word}'): '{actual_name}'")
            return actual_name

    return None


# ─────────────────────────────────────────────
#  LANGUAGE & TRANSCRIPTION
# ─────────────────────────────────────────────

def transcribe_audio_groq(audio_file):
    global detected_language
    try:
        with open(audio_file, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(audio_file, file.read()),
                model="whisper-large-v3",
                temperature=0.0,
                response_format="verbose_json"
            )
        whisper_lang = (getattr(transcription, 'language', 'english') or 'english').lower()
        detected_language = 'hi' if (whisper_lang.startswith('hi') or whisper_lang == 'urdu') else 'en'
        log(f"WHISPER_LANG: [{whisper_lang}] -> using [{detected_language}]")
        return transcription.text.strip()
    except Exception as e:
        log(f"STT Error: {e}")
        return ""


# ─────────────────────────────────────────────
#  QUANTITY EXTRACTION
# ─────────────────────────────────────────────

def extract_quantity(text, medicine_name=None):
    """
    Extract order quantity from text.
    KEY FIX: Strip numbers that are part of the medicine name before searching.
    e.g. "I want to order Liv 52" — remove "52" from medicine name first,
    so we don't accidentally order 52 units when user said no quantity.
    """
    search_text = text
    if medicine_name:
        med_numbers = re.findall(r'\b(\d+)\b', medicine_name)
        for n in med_numbers:
            search_text = re.sub(r'\b' + re.escape(n) + r'\b', '', search_text)
        search_text = re.sub(re.escape(medicine_name), '', search_text, flags=re.IGNORECASE)

    numbers = re.findall(r'\b(\d+)\b', search_text)
    if numbers:
        qty = int(numbers[0])
        log(f"QUANTITY extracted: {qty}")
        return qty

    word_to_num = {
        "one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,
        "eight":8,"nine":9,"ten":10,"fifteen":15,"twenty":20,"thirty":30,
        "fifty":50,"hundred":100,
        "एक":1,"दो":2,"तीन":3,"चार":4,"पांच":5,"पाँच":5,"छह":6,
        "सात":7,"आठ":8,"नौ":9,"दस":10,"पंद्रह":15,"बीस":20,"तीस":30,
        "पचास":50,"सौ":100
    }
    text_lower = search_text.lower()
    for word, num in word_to_num.items():
        if re.search(r'\b' + re.escape(word) + r'\b', text_lower):
            log(f"QUANTITY extracted (word): {num}")
            return num
    return None


# ─────────────────────────────────────────────
#  MEDICINE QUERY DETECTION
# ─────────────────────────────────────────────

def is_medicine_query(text):
    text_lower = text.lower()
    hospital_only = [
        "where is","location of","how to reach","visiting hours",
        "opd timing","lab timing","emergency department","emergency service",
        "लैब कहाँ","डॉक्टर से","अपॉइंटमेंट","ओपीडी टाइम","कहाँ है","कहां है"
    ]
    if any(kw in text_lower for kw in hospital_only):
        return False
    order_keywords = [
        "order","buy","purchase","want medicine","need medicine",
        "how much","price of","cost of","available","in stock",
        "ऑर्डर","खरीद","दवा चाहिए","दवाई चाहिए","गोली चाहिए",
        "कितने में","कीमत","उपलब्ध","मिलेगी","स्टॉक"
    ]
    if any(kw in text_lower for kw in order_keywords):
        return True
    if find_medicine_in_text(text):
        return True
    return False


# ─────────────────────────────────────────────
#  ORDER FLOW
# ─────────────────────────────────────────────

def handle_order_flow(user_text, caller_number, language):
    global pending_order
    text_lower = user_text.lower()

    R = {
        "hi": {
            "not_available": "माफ़ कीजिये, अभी हमारे पास {medicine} उपलब्ध नहीं है। क्या कुछ और चाहिए?",
            "low_stock": "हमारे पास केवल {stock} यूनिट {medicine} बची हैं। क्या आप सभी {stock} यूनिट ऑर्डर करना चाहेंगे?",
            "order_complete": "ऑर्डर कन्फर्म हो गया! {medicine} की {quantity} यूनिट, कुल ₹{total:.0f}। ऑर्डर नंबर {order_id}।",
            "ask_quantity": "{medicine} उपलब्ध है — ₹{price} प्रति यूनिट, {stock} यूनिट स्टॉक में। कितनी यूनिट चाहिए?",
            "quantity_question": "कितनी यूनिट चाहिए आपको?",
            "anything_else": "ठीक है। क्या मैं और कुछ मदद कर सकती हूं?",
            "info": "{medicine} की कीमत ₹{price} प्रति यूनिट है, {stock} यूनिट उपलब्ध हैं। क्या ऑर्डर करना चाहेंगे?",
        },
        "en": {
            "not_available": "Sorry, {medicine} is not available in our pharmacy right now. Would you like something else?",
            "low_stock": "We only have {stock} units of {medicine} in stock. Would you like to order all {stock} units?",
            "order_complete": "Order confirmed! {quantity} units of {medicine}, total ₹{total:.0f}. Order number: {order_id}.",
            "ask_quantity": "{medicine} is available at ₹{price} per unit. We have {stock} units in stock. How many would you like?",
            "quantity_question": "How many units would you like?",
            "anything_else": "No problem. Is there anything else I can help you with?",
            "info": "{medicine} costs ₹{price} per unit and we have {stock} units available. Would you like to place an order?",
        }
    }
    r = R[language]

    # If pending order exists, check if user is naming a DIFFERENT medicine
    if pending_order and pending_order.get('step') == 'ask_quantity':
        new_med = find_medicine_in_text(user_text)
        if new_med and new_med.lower() != pending_order['medicine'].lower():
            log(f"NEW medicine '{new_med}' overrides pending '{pending_order['medicine']}'")
            pending_order = None  # Start fresh

    # ── No pending order: detect medicine ──
    if pending_order is None:
        medicine = find_medicine_in_text(user_text)
        quantity = extract_quantity(user_text, medicine)

        if not medicine:
            return None

        available, stock, price, actual_name = check_medicine_availability(medicine)
        if not available:
            return r["not_available"].format(medicine=medicine)

        info_words = ["price","cost","how much","available","stock","quantity","info","tell me",
                      "कीमत","कितने में","उपलब्ध","स्टॉक","बताओ","जानकारी"]
        is_info = any(w in text_lower for w in info_words) and \
                  not any(w in text_lower for w in ["order","buy","ऑर्डर","चाहिए","लेना","करो"])

        if is_info and not quantity:
            pending_order = {'medicine': actual_name, 'stock': stock, 'price': price, 'step': 'ask_quantity'}
            return r["info"].format(medicine=actual_name, price=price, stock=stock)

        if quantity:
            if quantity > stock:
                pending_order = {'medicine': actual_name, 'quantity': quantity,
                                 'stock': stock, 'price': price, 'step': 'confirm_low_stock'}
                return r["low_stock"].format(stock=stock, medicine=actual_name)
            order_id = create_order(caller_number, actual_name, quantity)
            update_stock(actual_name, -quantity)
            return r["order_complete"].format(
                medicine=actual_name, quantity=quantity,
                total=price*quantity, order_id=order_id)

        pending_order = {'medicine': actual_name, 'stock': stock, 'price': price, 'step': 'ask_quantity'}
        return r["ask_quantity"].format(medicine=actual_name, price=price, stock=stock)

    # ── Waiting for quantity ──
    if pending_order['step'] == 'ask_quantity':
        quantity = extract_quantity(user_text, pending_order.get('medicine'))
        if not quantity:
            return r["quantity_question"]
        medicine, stock, price = pending_order['medicine'], pending_order['stock'], pending_order['price']
        if quantity > stock:
            pending_order.update({'quantity': quantity, 'step': 'confirm_low_stock'})
            return r["low_stock"].format(stock=stock, medicine=medicine)
        order_id = create_order(caller_number, medicine, quantity)
        update_stock(medicine, -quantity)
        total = price * quantity
        pending_order = None
        return r["order_complete"].format(medicine=medicine, quantity=quantity,
                                          total=total, order_id=order_id)

    # ── Low stock confirmation ──
    if pending_order['step'] == 'confirm_low_stock':
        yes = ["yes","ok","sure","yeah","confirm","alright","fine",
               "हाँ","हां","जी","ठीक","कन्फर्म","बिल्कुल"]
        if any(w in text_lower for w in yes):
            medicine, stock, price = pending_order['medicine'], pending_order['stock'], pending_order['price']
            order_id = create_order(caller_number, medicine, stock)
            update_stock(medicine, -stock)
            pending_order = None
            return r["order_complete"].format(medicine=medicine, quantity=stock,
                                              total=price*stock, order_id=order_id)
        pending_order = None
        return r["anything_else"]

    return None


# ─────────────────────────────────────────────
#  MAIN RESPONSE
# ─────────────────────────────────────────────

def get_groq_response(user_text, system_prompt=None, caller_number="unknown"):
    global current_caller, pending_order, detected_language
    current_caller = caller_number
    lang = detected_language

    # Medicine order takes priority
    if is_medicine_query(user_text) or pending_order:
        response = handle_order_flow(user_text, caller_number, lang)
        if response:
            conversation_history.append({"role": "user", "content": user_text})
            conversation_history.append({"role": "assistant", "content": response})
            return response

    if pending_order and not is_medicine_query(user_text):
        pending_order = None

    # Dynamic medicine list from DB for system prompt
    try:
        med_list = ", ".join(get_all_medicine_names())
    except:
        med_list = "Paracetamol, Aspirin, Ibuprofen, Cetirizine"

    system_prompts = {
        "hi": f"""आप Lucy हैं, सुभारती हॉस्पिटल, मीरत की सहायक AI।
जवाब हमेशा हिंदी में दें। जवाब 1-2 वाक्यों में रखें।

हॉस्पिटल जानकारी:
- OPD: गेट 2, ग्राउंड फ्लोर, सोम-शनि सुबह 8 से शाम 4 बजे
- इमरजेंसी: मुख्य प्रवेश द्वार (गोल चक्कर के सामने), 24/7
- लैब: मुख्य भवन, ग्राउंड फ्लोर, 8AM-4PM
- फार्मेसी: ग्राउंड फ्लोर गेट 3 के पास, 24/7
- हेल्पलाइन: 09639010313
- उपलब्ध दवाएं: {med_list}

नियम: मेडिकल सलाह न दें। गर्मजोशी से बात करें।""",

        "en": f"""You are Lucy, AI assistant for Subharti Hospital, Meerut, India.
Always respond in English. Keep responses to 1-2 sentences max (phone call).

Hospital Info:
- OPD: Gate 2, Ground Floor, Mon-Sat 8AM-4PM
- Emergency: Main Entrance (Gol Chakker front), 24/7
- Lab: Main Building, Ground Floor, 8AM-4PM
- Pharmacy: Ground Floor near Gate 3, 24/7
- Helpline: 09639010313
- Available medicines: {med_list}

Rules: No medical advice. Be warm and professional."""
    }

    if system_prompt is None:
        system_prompt = system_prompts[lang]

    conversation_history.append({"role": "user", "content": user_text})
    while len(conversation_history) > 16:
        conversation_history.pop(0)

    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "system", "content": system_prompt}, *conversation_history],
            model="llama-3.3-70b-versatile",
            temperature=0.6,
            max_tokens=100,
            stream=False
        )
        response = chat_completion.choices[0].message.content.strip()
        conversation_history.append({"role": "assistant", "content": response})
        return response
    except Exception as e:
        log(f"Groq AI Error: {e}")
        return ("मुझे अभी समस्या हो रही है। हेल्पलाइन 09639010313 पर कॉल करें।"
                if lang == "hi" else
                "I'm having trouble. Please call our helpline at 09639010313.")


def reset_conversation():
    global conversation_history, current_caller, pending_order, detected_language
    conversation_history = []
    current_caller = None
    pending_order = None
    detected_language = "en"
