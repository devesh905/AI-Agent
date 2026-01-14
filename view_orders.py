#!/usr/bin/env python3
"""
Simple CLI tool to view medicine orders and inventory
Run: python3 view_orders.py
"""

import sqlite3
import sys
from datetime import datetime

DB_PATH = "/home/devesh/ai-asterisk/data/medicine.db"

def view_all_orders():
    """Display all orders"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, caller_number, medicine_name, quantity, status, order_time
        FROM orders
        ORDER BY order_time DESC
    """)
    
    orders = cursor.fetchall()
    conn.close()
    
    if not orders:
        print("\n📦 No orders yet!\n")
        return
    
    print("\n" + "="*80)
    print("📦 MEDICINE ORDERS")
    print("="*80)
    print(f"{'ID':<5} {'Caller':<15} {'Medicine':<20} {'Qty':<5} {'Status':<10} {'Time':<20}")
    print("-"*80)
    
    for order in orders:
        order_id, caller, medicine, qty, status, order_time = order
        print(f"{order_id:<5} {caller:<15} {medicine:<20} {qty:<5} {status:<10} {order_time:<20}")
    
    print("="*80 + "\n")


def view_inventory():
    """Display medicine inventory"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT name, stock_quantity, price, last_updated
        FROM medicines
        ORDER BY name
    """)
    
    inventory = cursor.fetchall()
    conn.close()
    
    print("\n" + "="*80)
    print("💊 MEDICINE INVENTORY")
    print("="*80)
    print(f"{'Medicine':<25} {'Stock':<10} {'Price (₹)':<12} {'Last Updated':<20}")
    print("-"*80)
    
    for item in inventory:
        name, stock, price, updated = item
        stock_status = "✅ In Stock" if stock > 0 else "❌ Out of Stock"
        print(f"{name:<25} {stock:<10} {price:<12.2f} {updated:<20}")
    
    print("="*80 + "\n")


def add_stock():
    """Add stock to existing medicine"""
    print("\n📦 ADD STOCK")
    medicine = input("Enter medicine name: ").strip()
    quantity = int(input("Enter quantity to add: "))
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE medicines 
        SET stock_quantity = stock_quantity + ?,
            last_updated = CURRENT_TIMESTAMP
        WHERE LOWER(name) = LOWER(?)
    """, (quantity, medicine))
    
    if cursor.rowcount > 0:
        conn.commit()
        print(f"✅ Added {quantity} units to {medicine}")
    else:
        print(f"❌ Medicine '{medicine}' not found")
    
    conn.close()


def update_order_status():
    """Update order status"""
    print("\n📝 UPDATE ORDER STATUS")
    order_id = int(input("Enter order ID: "))
    print("Status options: pending, confirmed, delivered, cancelled")
    status = input("Enter new status: ").strip().lower()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE orders 
        SET status = ?
        WHERE id = ?
    """, (status, order_id))
    
    if cursor.rowcount > 0:
        conn.commit()
        print(f"✅ Order #{order_id} status updated to '{status}'")
    else:
        print(f"❌ Order #{order_id} not found")
    
    conn.close()


def main():
    """Main menu"""
    while True:
        print("\n" + "="*50)
        print("🏥 SUBHARTI MEDICINE ORDERING SYSTEM")
        print("="*50)
        print("1. View All Orders")
        print("2. View Inventory")
        print("3. Add Stock")
        print("4. Update Order Status")
        print("5. Exit")
        print("="*50)
        
        choice = input("\nEnter choice (1-5): ").strip()
        
        if choice == "1":
            view_all_orders()
        elif choice == "2":
            view_inventory()
        elif choice == "3":
            add_stock()
        elif choice == "4":
            update_order_status()
        elif choice == "5":
            print("\n👋 Goodbye!\n")
            break
        else:
            print("❌ Invalid choice")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!\n")
        sys.exit(0)
