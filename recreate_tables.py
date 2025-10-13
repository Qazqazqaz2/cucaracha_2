#!/usr/bin/env python3
"""
Script to recreate database tables with minimal schema
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DB_DSN = os.getenv("DB_DSN", "postgresql://postgres:762341@localhost:5432/cryptoindexator")

async def recreate_tables():
    """Recreate database tables with minimal schema"""
    print("Recreating database tables with minimal schema...")
    
    try:
        conn = await asyncpg.connect(DB_DSN)
        print("Connected to database")
        
        # Drop existing tables
        print("Dropping existing tables...")
        await conn.execute("DROP TABLE IF EXISTS pool_reserves CASCADE")
        await conn.execute("DROP TABLE IF EXISTS pools CASCADE")
        await conn.execute("DROP TABLE IF EXISTS jettons CASCADE")
        
        # Create tables with minimal schema
        print("Creating tables with minimal schema...")
        await conn.execute("""
        CREATE TABLE jettons (
          id SERIAL PRIMARY KEY,
          address TEXT UNIQUE NOT NULL,
          last_checked TIMESTAMP WITH TIME ZONE DEFAULT now()
        );
        """)
        
        await conn.execute("""
        CREATE TABLE pools (
          id SERIAL PRIMARY KEY,
          pool_address TEXT UNIQUE NOT NULL,
          token0_address TEXT NOT NULL,
          token1_address TEXT NOT NULL,
          lp_fee INT,
          protocol_fee INT,
          last_checked TIMESTAMP WITH TIME ZONE DEFAULT now()
        );
        """)
        
        await conn.execute("""
        CREATE TABLE pool_reserves (
          id SERIAL PRIMARY KEY,
          pool_id INT REFERENCES pools(id) ON DELETE CASCADE,
          reserve0 NUMERIC,
          reserve1 NUMERIC,
          checked_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        );
        """)
        
        print("Tables recreated successfully!")
        print("New schema:")
        print("- jettons: id, address, last_checked")
        print("- pools: id, pool_address, token0_address, token1_address, lp_fee, protocol_fee, last_checked")
        print("- pool_reserves: id, pool_id, reserve0, reserve1, checked_at")
        
    except Exception as e:
        print(f"Error recreating tables: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'conn' in locals():
            await conn.close()

if __name__ == "__main__":
    asyncio.run(recreate_tables())