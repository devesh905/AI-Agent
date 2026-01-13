def get_ai_response(text):
    text = text.lower()

    # Greetings
    if any(word in text for word in ["hello", "hi", "hey"]):
        return "Hello! How can I help you today?"
    
    # Balance inquiry
    if "balance" in text:
        return "Your account balance is five hundred rupees."
    
    # Thank you / goodbye
    if any(word in text for word in ["thank", "thanks", "bye", "goodbye"]):
        return "You're welcome! Have a great day!"
    
    # Transactions
    if "transaction" in text or "history" in text:
        return "Your last transaction was a deposit of one hundred rupees yesterday."
    
    # Default
    return "I can help with your balance and transactions. What would you like to know?"
