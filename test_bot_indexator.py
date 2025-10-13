#!/usr/bin/env python3
"""
Test script to verify bot works with updated indexator
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DB_DSN = os.getenv("DB_DSN", "postgresql://postgres:762341@localhost:5432/cryptoindexator")

# Test data
POPULAR_JETTONS = {
    "USDT": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs",
    "USDC": "EQBkzNV0DV5ZXtJzluUy1_jVdbZLXcESU_AHoYEW5p2O-kUS",
}

TON_MASTER = "EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c"

async def test_database_schema():
    """Test that the database schema is correct"""
    print("Testing database schema...")
    
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
        for col in jetton_columns:
            print(f"  {col['column_name']}: {col['data_type']}")
        
        # Check pools table schema
        pool_columns = await conn.fetch("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'pools'
            ORDER BY ordinal_position
        """)
        
        print("\nPools table columns:")
        for col in pool_columns:
            print(f"  {col['column_name']}: {col['data_type']}")
        
        # Check pool_reserves table schema
        reserve_columns = await conn.fetch("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'pool_reserves'
            ORDER BY ordinal_position
        """)
        
        print("\nPool_reserves table columns:")
        for col in reserve_columns:
            print(f"  {col['column_name']}: {col['data_type']}")
        
        # Test inserting test data
        print("\nTesting data insertion...")
        
        # Insert a jetton
        for symbol, address in POPULAR_JETTONS.items():
            await conn.execute("""
                INSERT INTO jettons (address, last_checked)
                VALUES ($1, now())
                ON CONFLICT (address) DO UPDATE SET last_checked = now()
            """, address)
            print(f"  Inserted/updated jetton {symbol}: {address}")
        
        # Insert a pool
        usdt_address = POPULAR_JETTONS["USDT"]
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
        usdt_address,
        TON_MASTER,
        30, 0)
        print("  Inserted/updated pool")
        
        # Insert pool reserves
        pool = await conn.fetchrow("""
            SELECT id FROM pools WHERE token0_address = $1 AND token1_address = $2
        """, usdt_address, TON_MASTER)
        
        if pool:
            await conn.execute("""
                INSERT INTO pool_reserves (pool_id, reserve0, reserve1, checked_at)
                VALUES ($1, $2, $3, now())
            """, pool["id"], 1000000, 5000000, "now()")
            print("  Inserted pool reserves")
        
        # Test querying data
        print("\nTesting data query...")
        
        # Query jettons
        jetton_count = await conn.fetchval("SELECT COUNT(*) FROM jettons")
        print(f"  Jettons count: {jetton_count}")
        
        # Query pools
        pool_count = await conn.fetchval("SELECT COUNT(*) FROM pools")
        print(f"  Pools count: {pool_count}")
        
        # Query reserves
        reserve_count = await conn.fetchval("SELECT COUNT(*) FROM pool_reserves")
        print(f"  Reserves count: {reserve_count}")
        
        print("\n✓ Database schema test completed successfully!")
        
    except Exception as e:
        print(f"Error testing database schema: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'conn' in locals():
            await conn.close()

async def test_price_calculation():
    """Test price calculation function"""
    print("\nTesting price calculation...")
    
    try:
        conn = await asyncpg.connect(DB_DSN)
        
        # Test price calculation for USDT/TON
        usdt_address = POPULAR_JETTONS["USDT"]
        
        # Find pool
        pool = await conn.fetchrow("""
            SELECT p.id, p.token0_address, p.token1_address
            FROM pools p
            WHERE (p.token0_address = $1 AND p.token1_address = $2)
               OR (p.token0_address = $2 AND p.token1_address = $1)
            LIMIT 1
        """, usdt_address, TON_MASTER)
        
        if pool:
            print(f"  Found pool: {pool}")
            
            # Get reserves
            reserves = await conn.fetchrow("""
                SELECT reserve0, reserve1
                FROM pool_reserves
                WHERE pool_id = $1
                ORDER BY checked_at DESC
                LIMIT 1
            """, pool["id"])
            
            if reserves:
                r0, r1 = reserves["reserve0"], reserves["reserve1"]
                print(f"  Reserves: {r0}, {r1}")
                
                # Calculate price
                if pool["token0_address"] == usdt_address and pool["token1_address"] == TON_MASTER:
                    price = r1 / r0 if r0 and r0 > 0 else None
                else:
                    price = r0 / r1 if r1 and r1 > 0 else None
                
                if price:
                    print(f"  Calculated price: {price:.6f} TON per USDT")
                else:
                    print("  Could not calculate price")
            else:
                print("  No reserves found")
        else:
            print("  No pool found")
        
        print("\n✓ Price calculation test completed!")
        
    except Exception as e:
        print(f"Error in price calculation test: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'conn' in locals():
            await conn.close()

if __name__ == "__main__":
    asyncio.run(test_database_schema())
    asyncio.run(test_price_calculation())