#!/usr/bin/env python3
"""
Demonstration script for the chart data collection system
"""

import sqlite3
import time
from datetime import datetime
import sys
import os

# Add the current directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot import init_db, update_token_database, chart_data_collector, generate_price_chart

def demonstrate_system():
    print("=== Chart Data Collection System Demonstration ===\n")
    
    # Initialize database
    print("1. Initializing database...")
    init_db()
    print("   Database initialized successfully\n")
    
    # Update token database
    print("2. Updating token database...")
    update_token_database()
    print("   Token database updated\n")
    
    # Show database structure
    print("3. Database structure:")
    conn = sqlite3.connect('tokens.db')
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA table_info(tokens);")
    token_columns = cursor.fetchall()
    print("   Tokens table columns:")
    for col in token_columns:
        print(f"     - {col[1]} ({col[2]})")
    
    cursor.execute("PRAGMA table_info(chart_data);")
    chart_columns = cursor.fetchall()
    print("   Chart data table columns:")
    for col in chart_columns:
        print(f"     - {col[1]} ({col[2]})")
    
    conn.close()
    print()
    
    # Show initial data count
    conn = sqlite3.connect('tokens.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM chart_data;")
    initial_count = cursor.fetchone()[0]
    conn.close()
    print(f"4. Initial chart data points: {initial_count}\n")
    
    # Collect some data (just one cycle)
    print("5. Collecting chart data for one cycle...")
    try:
        # We'll manually run one cycle of the collector
        print("   Starting chart data collection cycle")
        
        # Update token database to ensure we have the latest tokens
        update_token_database()
        
        # Get a few tokens from the database (just test with first 5 for demo)
        conn = sqlite3.connect('tokens.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT contract_address FROM tokens 
            WHERE contract_address != "EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c"
            LIMIT 5
        ''')
        token_addresses = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        print(f"   Found {len(token_addresses)} tokens to process (demo limited to 5)")
        
        # Process just one token for demo
        if token_addresses:
            contract_address = token_addresses[0]
            print(f"   Processing token: {contract_address}")
            
            # This is a simplified version of what chart_data_collector does
            from bot import save_price_data
            import requests
            import random
            
            # Simulate getting a price (in real system this comes from pool data)
            simulated_price = random.uniform(0.0001, 100.0)
            save_price_data(contract_address, simulated_price)
            print(f"   Saved price data: {simulated_price}")
        
        print("   Chart data collection cycle completed\n")
        
    except Exception as e:
        print(f"   Error in data collection: {e}\n")
    
    # Show final data count
    conn = sqlite3.connect('tokens.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM chart_data;")
    final_count = cursor.fetchone()[0]
    conn.close()
    print(f"6. Final chart data points: {final_count} (+{final_count - initial_count})\n")
    
    # Generate a chart using stored data
    print("7. Generating chart using stored data...")
    try:
        chart_data = generate_price_chart("DEMO", None, 24)
        with open("demo_chart.png", "wb") as f:
            f.write(chart_data)
        print(f"   Chart generated successfully ({len(chart_data)} bytes)")
        print("   Chart saved as demo_chart.png\n")
    except Exception as e:
        print(f"   Error generating chart: {e}\n")
    
    print("=== Demonstration Complete ===")
    print("\nTo see the full system in action:")
    print("1. Run the bot continuously")
    print("2. The chart_data_collector will run every minute")
    print("3. Price data will accumulate in the database")
    print("4. Charts will use this stored data for better performance")

if __name__ == "__main__":
    demonstrate_system()