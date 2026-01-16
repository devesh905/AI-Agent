#!/usr/bin/env python3
"""
Smart AI with proper medicine ordering flow
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
pending_order = None  # Store pending order state: {'medicine': str, 'quantity': int, 'step': str}


def transcribe_audio_groq(audio_file):
    """Transcribe audio using Groq Whisper"""
    try:
        with open(audio_file, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(audio_file, file.read()),
                model="whisper-large-v3",
                language="en",
                temperature=0.0,
                response_format="json"
            )
        return transcription.text.strip()
    except Exception as e:
        print(f"Groq STT Error: {e}")
        return ""


def extract_quantity(text):
    """Extract quantity from text"""
    text_lower = text.lower()
    
    # Look for number patterns
    words = text_lower.split()
    for i, word in enumerate(words):
        # Direct number
        if word.isdigit():
            return int(word)
        
        # Number before "unit" or "units"
        if i > 0 and words[i] in ["unit", "units", "piece", "pieces", "tablet", "tablets"]:
            if words[i-1].isdigit():
                return int(words[i-1])
    
    # Word numbers
    word_to_num = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "ten": 10, "twenty": 20, "thirty": 30, "fifty": 50, "hundred": 100
    }
    
    for word, num in word_to_num.items():
        if word in text_lower:
            return num
    
    return None


def is_medicine_query(text):
    """Check if text is about medicines (not hospital info)"""
    text_lower = text.lower()
    
    # Hospital info keywords
    hospital_keywords = [
        "lab", "scan", "test", "doctor", "appointment", "opd", "emergency",
        "where", "location", "direction", "how to reach", "timing", "hours",
        "department", "ward", "admission", "visiting", "pharmacy location"
    ]
    
    # If it's clearly about hospital, return False
    if any(keyword in text_lower for keyword in hospital_keywords):
        return False
    
    # Medicine order keywords
    medicine_keywords = [
        "order", "buy", "medicine", "tablet", "drug", "available",
        "stock", "paracetamol", "aspirin", "ibuprofen", "cetirizine",
        "dolo", "crocin", "combiflam", "citrigen", "disprin"
    ]
    
    return any(keyword in text_lower for keyword in medicine_keywords)


def extract_medicine_name(text):
    """Extract medicine name from text"""
    text_lower = text.lower()
    
    # Known medicines
    known_medicines = [
        "paracetamol", "aspirin", "ibuprofen", "amoxicillin",
        "cetirizine", "dolo", "crocin", "combiflam", "citrigen",
        "disprin", "avil", "azithromycin"
    ]
    
    for med in known_medicines:
        if med in text_lower:
            return med
    
    # Try to extract unknown medicine name
    order_words = ["order", "buy", "want", "need", "get"]
    words = text_lower.split()
    
    for i, word in enumerate(words):
        if word in order_words and i + 1 < len(words):
            potential_med = words[i + 1]
            # Skip common words
            skip_words = ["to", "some", "a", "the", "medicine", "tablet", "drug"]
            if potential_med not in skip_words and len(potential_med) > 3:
                return potential_med
    
    return None


def handle_order_flow(user_text, caller_number):
    """
    Handle medicine ordering with proper conversation flow
    Returns: response_text
    """
    global pending_order
    
    text_lower = user_text.lower()
    
    # === STEP 1: Initial order request ===
    if pending_order is None:
        medicine = extract_medicine_name(user_text)
        quantity = extract_quantity(user_text)
        
        if not medicine:
            return None  # Let normal AI handle it
        
        # Check if medicine exists
        available, stock, price, actual_name = check_medicine_availability(medicine)
        
        if not available:
            # Don't create garbage orders
            return (f"I'm sorry, we don't have {medicine} in our pharmacy. "
                   f"Would you like to order something else?")
        
        # If quantity specified in first message
        if quantity:
            if quantity > stock:
                pending_order = {
                    'medicine': actual_name,
                    'quantity': quantity,
                    'stock': stock,
                    'price': price,
                    'step': 'confirm_low_stock'
                }
                return (f"We only have {stock} units of {actual_name} available. "
                       f"Would you like to order all {stock} units?")
            else:
                # Complete order immediately
                order_id = create_order(caller_number, actual_name, quantity)
                update_stock(actual_name, -quantity)
                total = price * quantity
                return (f"Perfect! {actual_name} is available. "
                       f"Your order for {quantity} units (₹{total}) is confirmed. "
                       f"Order number: {order_id}.")
        
        # Ask for quantity
        pending_order = {
            'medicine': actual_name,
            'stock': stock,
            'price': price,
            'step': 'ask_quantity'
        }
        
        return (f"Yes, {actual_name} is available at ₹{price} per unit. "
               f"We have {stock} units in stock. How many would you like?")
    
    # === STEP 2: User provides quantity ===
    if pending_order['step'] == 'ask_quantity':
        quantity = extract_quantity(user_text)
        
        if not quantity:
            return "How many units would you like to order?"
        
        medicine = pending_order['medicine']
        stock = pending_order['stock']
        price = pending_order['price']
        
        if quantity > stock:
            pending_order['quantity'] = quantity
            pending_order['step'] = 'confirm_low_stock'
            return (f"We only have {stock} units available. "
                   f"Would you like to order all {stock} units instead?")
        
        # Complete order
        order_id = create_order(caller_number, medicine, quantity)
        update_stock(medicine, -quantity)
        total = price * quantity
        
        pending_order = None  # Reset
        
        return (f"Great! Your order for {quantity} units of {medicine} (₹{total}) is confirmed. "
               f"Order number: {order_id}.")
    
    # === STEP 3: Handle low stock confirmation ===
    if pending_order['step'] == 'confirm_low_stock':
        if any(word in text_lower for word in ["yes", "ok", "sure", "yeah", "confirm"]):
            medicine = pending_order['medicine']
            stock = pending_order['stock']
            price = pending_order['price']
            
            order_id = create_order(caller_number, medicine, stock)
            update_stock(medicine, -stock)
            total = price * stock
            
            pending_order = None
            
            return (f"Done! Your order for {stock} units of {medicine} (₹{total}) is confirmed. "
                   f"Order number: {order_id}.")
        else:
            pending_order = None
            return "No problem. Is there anything else I can help you with?"
    
    return None


def get_groq_response(user_text, system_prompt=None, caller_number="unknown"):
    """Enhanced AI with smart ordering"""
    global current_caller, pending_order
    current_caller = caller_number
    
    # Check if this is a medicine order
    if is_medicine_query(user_text):
        response = handle_order_flow(user_text, caller_number)
        if response:
            conversation_history.append({"role": "user", "content": user_text})
            conversation_history.append({"role": "assistant", "content": response})
            return response
    
    # Reset pending order if user changes topic
    if pending_order and not is_medicine_query(user_text):
        pending_order = None
    
    # Normal AI response for hospital info
    if system_prompt is None:
        system_prompt = """You are Lucy, a helpful AI assistant for Subharti Hospital in Meerut, India.

IMPORTANT: Keep responses SHORT (1-2 sentences). This is a phone call.

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
- For medicine orders, I handle them separately
- Keep responses natural and conversational
"""
    
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
        return "I'm having trouble. Please call our helpline at 09639010313."


def reset_conversation():
    """Reset for new call"""
    global conversation_history, current_caller, pending_order
    conversation_history = []
    current_caller = None
    pending_order = None
