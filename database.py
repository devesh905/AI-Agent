#!/usr/bin/env python3
"""
Database handler for medicine ordering system
Keeps your existing functionality intact
"""

import sqlite3
import os
from datetime import datetime

# Database path
DB_PATH = "/home/devesh/ai-asterisk/data/medicine.db"
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

def init_database():
    """Initialize database tables on first run"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Medicine inventory table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS medicines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            stock_quantity INTEGER DEFAULT 0,
            price REAL DEFAULT 0.0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Orders table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            caller_number TEXT,
            medicine_name TEXT NOT NULL,
            quantity INTEGER DEFAULT 1,
            status TEXT DEFAULT 'pending',
            order_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            delivery_address TEXT,
            FOREIGN KEY (medicine_name) REFERENCES medicines(name)
        )
    """)
    
    # Add some sample medicines
    sample_medicines = [
        ("Paracetamol", 100, 5.0),
        ("Aspirin", 50, 10.0),
        ("Ibuprofen", 75, 8.0),
        ("Amoxicillin", 30, 50.0),
        ("Cetirizine", 60, 3.0)
    ]
    
    for name, stock, price in sample_medicines:
        cursor.execute("""
            INSERT OR IGNORE INTO medicines (name, stock_quantity, price)
            VALUES (?, ?, ?)
        """, (name, stock, price))
    
    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")


def check_medicine_availability(medicine_name):
    """
    Check if medicine is available in stock
    Returns: (available: bool, stock: int, price: float)
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Fuzzy search - case insensitive
    cursor.execute("""
        SELECT name, stock_quantity, price 
        FROM medicines 
        WHERE LOWER(name) LIKE LOWER(?)
    """, (f"%{medicine_name}%",))
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
        name, stock, price = result
        return True, stock, price, name
    else:
        return False, 0, 0.0, None


def add_medicine_to_inventory(medicine_name, quantity=0, price=0.0):
    """
    Add new medicine to inventory
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO medicines (name, stock_quantity, price)
            VALUES (?, ?, ?)
        """, (medicine_name.title(), quantity, price))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        # Medicine already exists
        conn.close()
        return False


def create_order(caller_number, medicine_name, quantity=1, address=""):
    """
    Create a new medicine order
    Returns: order_id
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO orders (caller_number, medicine_name, quantity, delivery_address)
        VALUES (?, ?, ?, ?)
    """, (caller_number, medicine_name, quantity, address))
    
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return order_id


def update_stock(medicine_name, quantity_change):
    """
    Update medicine stock (positive to add, negative to reduce)
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE medicines 
        SET stock_quantity = stock_quantity + ?,
            last_updated = CURRENT_TIMESTAMP
        WHERE LOWER(name) = LOWER(?)
    """, (quantity_change, medicine_name))
    
    conn.commit()
    conn.close()


def get_order_history(caller_number):
    """Get all orders for a caller"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, medicine_name, quantity, status, order_time
        FROM orders
        WHERE caller_number = ?
        ORDER BY order_time DESC
        LIMIT 5
    """, (caller_number,))
    
    orders = cursor.fetchall()
    conn.close()
    return orders


# Initialize database when module loads
init_database()
