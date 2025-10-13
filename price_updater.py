# price_updater.py
import asyncio
import logging
from bot import init_db, populate_tokens, update_prices, DB_FILE, ASSETS_URL, POOLS_URL
import aiohttp

logging.basicConfig(level=logging.INFO)

async def main():
    await init_db()
    async with aiohttp.ClientSession() as session:
        await populate_tokens(session)
        await update_prices(session)  # здесь цикл, будет работать бесконечно

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped by user")
