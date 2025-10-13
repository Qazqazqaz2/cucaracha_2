import asyncio
import asyncpg

# Database
DB_DSN = "postgresql://postgres:762341@localhost:5432/cryptoindexator"

async def test_db_connection():
    """Test database connection and fetch some jetton addresses"""
    try:
        conn = await asyncpg.connect(DB_DSN)
        rows = await conn.fetch("SELECT address FROM jettons LIMIT 3")
        await conn.close()
        
        print("Jetton addresses in DB:")
        for row in rows:
            print(f"  {row['address']}")
        return [row['address'] for row in rows]
    except Exception as e:
        print(f"Error connecting to DB: {e}")
        return []

async def main():
    addresses = await test_db_connection()
    print(f"\nFound {len(addresses)} jetton addresses")

if __name__ == "__main__":
    asyncio.run(main())