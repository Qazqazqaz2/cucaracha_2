#!/usr/bin/env python3
"""
Test script to verify concurrent database operations work correctly
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DB_DSN = os.getenv("DB_DSN", "postgresql://postgres:762341@localhost:5432/cryptoindexator")

async def test_concurrent_operations():
    """Test concurrent database operations"""
    print("Testing concurrent database operations...")
    
    try:
        # Create initial connection
        conn = await asyncpg.connect(DB_DSN)
        print("Connected to database")
        
        # Insert test data
        await conn.execute("""
            INSERT INTO jettons (address, last_checked)
            VALUES ($1, now())
            ON CONFLICT (address) DO NOTHING
        """, "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs")
        
        await conn.execute("""
            INSERT INTO pools (pool_address, token0_address, token1_address, lp_fee, protocol_fee, last_checked)
            VALUES ($1, $2, $3, $4, $5, now())
            ON CONFLICT (pool_address) DO NOTHING
        """, 
        "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs_pool",
        "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs_token0",
        "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs_token1",
        30, 0)
        
        await conn.close()
        
        # Test concurrent operations with separate connections
        async def worker(worker_id):
            worker_conn = await asyncpg.connect(DB_DSN)
            try:
                # Simulate some work
                await asyncio.sleep(0.1)
                
                # Perform database operation
                result = await worker_conn.fetchval("""
                    SELECT COUNT(*) FROM jettons
                """)
                print(f"Worker {worker_id}: Found {result} jettons")
                
                # Update a record
                await worker_conn.execute("""
                    UPDATE pools SET last_checked = now() WHERE pool_address = $1
                """, "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs_pool")
                
                print(f"Worker {worker_id}: Updated pool timestamp")
            finally:
                await worker_conn.close()
        
        # Run multiple workers concurrently
        workers = [worker(i) for i in range(5)]
        await asyncio.gather(*workers)
        
        print("✓ All concurrent operations completed successfully!")
        
    except Exception as e:
        print(f"Error during concurrent operations test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_concurrent_operations())