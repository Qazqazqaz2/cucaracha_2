#!/usr/bin/env python3
"""
Database migration script to update schema for minimal token storage
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DB_DSN = "postgresql://postgres:762341@localhost:5432/cryptoindexator"

async def migrate_database():
    """Migrate the database schema to store only minimal token information"""
    print("Starting database migration...")
    
    try:
        conn = await asyncpg.connect(DB_DSN)
        print("Connected to database")
        
        # Check if migration is needed by seeing if old columns exist
        columns = await conn.fetch("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'jettons' AND column_name IN ('symbol', 'name', 'decimals', 'total_supply')
        """)
        
        if columns:
            print("Old schema detected. Migrating to minimal schema...")
            
            # Remove columns that are no longer needed
            # Since we can't directly drop columns in PostgreSQL, we'll create a new table
            print("Creating new jettons table with minimal schema...")
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS jettons_new (
                    id SERIAL PRIMARY KEY,
                    address TEXT UNIQUE NOT NULL,
                    last_checked TIMESTAMP WITH TIME ZONE DEFAULT now()
                )
            """)
            
            # Copy data from old table to new table
            print("Copying data to new table...")
            await conn.execute("""
                INSERT INTO jettons_new (id, address, last_checked)
                SELECT id, address, last_checked FROM jettons
                ON CONFLICT (address) DO NOTHING
            """)
            
            # Drop old table and rename new one
            print("Replacing old table with new one...")
            await conn.execute("DROP TABLE jettons")
            await conn.execute("ALTER TABLE jettons_new RENAME TO jettons")
            
            print("Jettons table migrated successfully!")
        else:
            print("Jettons table already has minimal schema")
        
        # Check pools table
        pool_columns = await conn.fetch("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'pools'
        """)
        print(f"Pools table columns: {[col['column_name'] for col in pool_columns]}")
        
        print("Database migration completed successfully!")
        
    except Exception as e:
        print(f"Error during migration: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'conn' in locals():
            await conn.close()

if __name__ == "__main__":
    asyncio.run(migrate_database())