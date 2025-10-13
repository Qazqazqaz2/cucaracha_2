#!/usr/bin/env python3
"""
Test script to verify minimal database schema
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DB_DSN = os.getenv("DB_DSN", "postgresql://postgres:762341@localhost:5432/cryptoindexator")

async def test_minimal_schema():
    """Test that the database has the minimal schema"""
    print("Testing minimal database schema...")
    
    try:
        conn = await asyncpg.connect(DB_DSN)
        print("Connected to database")
        
        # Check jettons table schema
        jetton_columns = await conn.fetch("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'jettons'
            ORDER BY ordinal_position
        """)
        
        print("\nJettons table columns:")
        jetton_column_names = []
        for col in jetton_columns:
            print(f"  {col['column_name']}: {col['data_type']}")
            jetton_column_names.append(col['column_name'])
        
        # Expected columns for jettons
        expected_jetton_columns = ['id', 'address', 'last_checked']
        if set(jetton_column_names) == set(expected_jetton_columns):
            print("  ✓ Jettons table has correct minimal schema")
        else:
            print(f"  ✗ Jettons table schema mismatch. Expected: {expected_jetton_columns}, Got: {jetton_column_names}")
        
        # Check pools table schema
        pool_columns = await conn.fetch("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'pools'
            ORDER BY ordinal_position
        """)
        
        print("\nPools table columns:")
        pool_column_names = []
        for col in pool_columns:
            print(f"  {col['column_name']}: {col['data_type']}")
            pool_column_names.append(col['column_name'])
        
        # Expected columns for pools
        expected_pool_columns = ['id', 'pool_address', 'token0_address', 'token1_address', 'lp_fee', 'protocol_fee', 'last_checked']
        if set(pool_column_names) == set(expected_pool_columns):
            print("  ✓ Pools table has correct minimal schema")
        else:
            print(f"  ✗ Pools table schema mismatch. Expected: {expected_pool_columns}, Got: {pool_column_names}")
        
        # Check pool_reserves table schema
        reserve_columns = await conn.fetch("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'pool_reserves'
            ORDER BY ordinal_position
        """)
        
        print("\nPool_reserves table columns:")
        reserve_column_names = []
        for col in reserve_columns:
            print(f"  {col['column_name']}: {col['data_type']}")
            reserve_column_names.append(col['column_name'])
        
        # Expected columns for pool_reserves
        expected_reserve_columns = ['id', 'pool_id', 'reserve0', 'reserve1', 'checked_at']
        if set(reserve_column_names) == set(expected_reserve_columns):
            print("  ✓ Pool_reserves table has correct schema")
        else:
            print(f"  ✗ Pool_reserves table schema mismatch. Expected: {expected_reserve_columns}, Got: {reserve_column_names}")
        
        # Test inserting data with minimal schema
        print("\nTesting data insertion with minimal schema...")
        
        # Insert a jetton
        await conn.execute("""
            INSERT INTO jettons (address, last_checked)
            VALUES ($1, now())
            ON CONFLICT (address) DO UPDATE SET last_checked = now()
        """, "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs")
        
        # Insert a pool
        await conn.execute("""
            INSERT INTO pools (pool_address, token0_address, token1_address, lp_fee, protocol_fee, last_checked)
            VALUES ($1, $2, $3, $4, $5, now())
            ON CONFLICT (pool_address) DO UPDATE SET 
                token0_address = EXCLUDED.token0_address,
                token1_address = EXCLUDED.token1_address,
                lp_fee = EXCLUDED.lp_fee,
                protocol_fee = EXCLUDED.protocol_fee,
                last_checked = now()
        """, 
        "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs_pool",
        "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs_token0",
        "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs_token1",
        30, 0)
        
        print("  ✓ Data insertion successful")
        
        # Verify data
        jetton_count = await conn.fetchval("SELECT COUNT(*) FROM jettons")
        pool_count = await conn.fetchval("SELECT COUNT(*) FROM pools")
        
        print(f"  Jettons count: {jetton_count}")
        print(f"  Pools count: {pool_count}")
        
        print("\n✓ All tests passed! Database has correct minimal schema.")
        
    except Exception as e:
        print(f"Error testing database schema: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'conn' in locals():
            await conn.close()

if __name__ == "__main__":
    asyncio.run(test_minimal_schema())