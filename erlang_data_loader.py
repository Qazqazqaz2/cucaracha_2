#!/usr/bin/env python3
"""
Python script to load data collected by Erlang collector into the database
"""

import sqlite3
import json
import time
import os
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Database file
DB_FILE = 'tokens.db'
DATA_FILE = 'erlang_collected_data.json'

def init_db():
    """Initialize the database with chart_data table if it doesn't exist"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Create chart_data table for storing price history if it doesn't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chart_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_address TEXT,
            timestamp INTEGER,
            price REAL,
            FOREIGN KEY (contract_address) REFERENCES tokens (contract_address)
        )
    ''')
    
    # Create index for faster queries if it doesn't exist
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_chart_data_contract_timestamp 
        ON chart_data (contract_address, timestamp)
    ''')
    
    conn.commit()
    conn.close()

def load_erlang_data():
    """Load data collected by Erlang collector and store in database"""
    try:
        # Check if data file exists
        if not os.path.exists(DATA_FILE):
            logger.info(f"Data file {DATA_FILE} not found")
            return
            
        # Read data from file
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
        
        # Initialize database
        init_db()
        
        # Store data in database
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        inserted_count = 0
        for item in data:
            if isinstance(item, list) and len(item) >= 3:
                contract_address, price, timestamp = item[0], item[1], item[2]
                
                # Insert data into chart_data table
                cursor.execute('''
                    INSERT INTO chart_data (contract_address, timestamp, price)
                    VALUES (?, ?, ?)
                ''', (contract_address, int(timestamp), float(price)))
                inserted_count += 1
        
        conn.commit()
        conn.close()
        
        logger.info(f"Loaded {inserted_count} price data points from Erlang collector")
        
        # Remove the data file after processing
        os.remove(DATA_FILE)
        logger.info(f"Removed processed data file {DATA_FILE}")
        
    except Exception as e:
        logger.error(f"Error loading Erlang data: {e}")

def main():
    while True:
        if os.path.exists('erlang_collected_data.json'):
            with open('erlang_collected_data.json', 'r') as f:
                data = json.load(f)
            # Process each [token, price, timestamp] and call save_price_data(token, price)
            logging.info(f"Loaded {len(data)} price points")
            os.remove('erlang_collected_data.json')  # Or rename to .processed
        else:
            logging.info("Data file erlang_collected_data.json not found")
        time.sleep(30)

if __name__ == "__main__":
    main()