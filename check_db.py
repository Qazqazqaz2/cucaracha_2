import asyncio
import asyncpg

async def test():
    conn = await asyncpg.connect('postgresql://postgres:762341@localhost:5432/cryptoindexator')
    rows = await conn.fetch('SELECT address FROM jettons LIMIT 5')
    print('Jetton addresses in DB:')
    for row in rows:
        print(row['address'])
    await conn.close()

if __name__ == "__main__":
    asyncio.run(test())