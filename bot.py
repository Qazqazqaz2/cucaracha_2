import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import asyncpg
import aiohttp
import re

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ston-bot")

# Telegram bot token
BOT_TOKEN = "7620805227:AAE4pjop_z-2uFjh-B76ShT0agNzyCe22H8"

# Database
DB_DSN = "postgresql://postgres:762341@localhost:5432/cryptoindexator"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Хранилище для пользовательских выборов
user_choices = {}

# Кэш для известных токенов
KNOWN_TOKENS = {
    "EQAzb42FJ9Jl3hznJiE1wMv-uYnArKs079cwjJq7CY46n_4M": {
        "symbol": "AKO",
        "name": "Akorbital",
        "decimals": 9,
        "description": "Akorbital Token"
    },
    "EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c": {
        "symbol": "TON",
        "name": "Toncoin",
        "decimals": 9,
        "description": "Native TON token"
    },
    "EQD26zcd6Cqpz7WyLKVH8x_cD6D7tBrom6hKcycv8L8hV0GP": {
        "symbol": "USDT",
        "name": "Tether USD",
        "decimals": 6,
        "description": "Tether USD on TON"
    },
    "EQBX6K9aXVl3nXINCyPPL86C4ONVmQ8vK360u6dykFKXpHCa": {
        "symbol": "USDC",
        "name": "USD Coin",
        "decimals": 6,
        "description": "USD Coin on TON"
    },
    "EQAgQKzQidR3QLNsMkHtkx-VafzA4VPmCI0G-ZWJWfaNpalu": {
        "symbol": "NOT",
        "name": "Notcoin",
        "decimals": 9,
        "description": "Notcoin"
    }
}


async def get_jetton_addresses_from_db() -> dict:
    """Получает адреса Jetton контрактов из базы данных"""
    try:
        conn = await asyncpg.connect(DB_DSN)
        rows = await conn.fetch("SELECT address FROM jettons LIMIT 10")
        await conn.close()

        jettons = {}
        for i, row in enumerate(rows):
            symbol = f"TOKEN{i+1}"
            jettons[symbol] = row["address"]
        return jettons
    except Exception as e:
        logger.error(f"Error fetching from DB: {e}")
        return {}


def convert_to_raw_address(user_friendly_addr: str) -> str:
    """Конвертирует адрес в raw format"""
    if user_friendly_addr.startswith('EQ'):
        return user_friendly_addr[2:]  # Убираем 'EQ'
    return user_friendly_addr


async def get_jetton_metadata_from_tonapi(jetton_address: str) -> dict:
    """Получает метаданные из tonapi.io"""
    try:
        raw_addr = convert_to_raw_address(jetton_address)
        print(f"Getting metadata for {jetton_address}")
        print(f"raw_addr: {raw_addr}")
        url = f"https://tonapi.io/v2/jettons/{jetton_address}"
        print(url)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                print(response.status)
                if response.status == 200:
                    data = await response.json()
                    return {
                        "symbol": data.get('metadata', {}).get('symbol', 'UNKNOWN'),
                        "name": data.get('metadata', {}).get('name', 'Unknown Token'),
                        "decimals": data.get('decimals', 9),
                        "description": data.get('metadata', {}).get('description', ''),
                        "verified": data.get('verified', False)
                    }
    except Exception as e:
        logger.debug(f"tonapi.io error for {jetton_address}: {e}")
    return None


async def get_jetton_metadata(jetton_address: str) -> dict:

    metadata = await get_jetton_metadata_from_tonapi(jetton_address)
    if metadata:
        return metadata

    return {
        "symbol": "UNKNOWN",
        "name": "Unknown Token",
        "decimals": 9,
        "description": "",
        "verified": False
    }


async def get_jetton_price_from_stonfi(jetton_address: str) -> tuple:
    """Получает цену токена из STON.fi"""
    try:
        url = f"https://api.ston.fi/v1/tokens/{jetton_address}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                print(response.status)
                if response.status == 200:
                    data = await response.json()
                    print(data)
                    price = data.get('price')
                    if price:
                        return float(price), "STON.fi"
    except Exception as e:
        logger.debug(f"STON.fi price error for {jetton_address}: {e}")

    return None, None


async def get_jetton_price_from_dedust(jetton_address: str) -> tuple:
    """Получает цену токена из DeDust.io"""
    try:
        url = "https://api.dedust.io/v2/pools"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    pools = await response.json()
                    for pool in pools:
                        assets = pool.get("assets", [])
                        if len(assets) != 2:
                            continue
                        asset_addresses = [a.get("address") for a in assets]
                        
                        if jetton_address not in asset_addresses:
                            continue

                        reserves = pool.get("reserves", {})
                        ton_reserve = None
                        token_reserve = None
                        for asset in assets:
                            addr = asset.get("address")
                            if addr == "EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c":  # TON
                                ton_reserve = reserves.get(addr)
                            elif addr==jetton_address:
                                token_reserve = reserves.get(addr)

                        if ton_reserve and token_reserve:
                            price = float(ton_reserve) / float(token_reserve)
                            return price, "DeDust"
    except Exception as e:
        logger.debug(f"DeDust.io price error for {jetton_address}: {e}")

    return None, None


async def get_jetton_price(jetton_address: str) -> tuple:
    """Получает цену токена из STON.fi или DeDust"""
    price, source = await get_jetton_price_from_stonfi(jetton_address)
    if price:
        return price, source

    price, source = await get_jetton_price_from_dedust(jetton_address)
    if price:
        return price, source

    return None, None


def build_token_keyboard(jetton_address: str) -> types.InlineKeyboardMarkup:
    """Создает inline-кнопки для токена"""
    buttons = [
        [types.InlineKeyboardButton(text="🔄 Refresh", callback_data=f"refresh_{jetton_address}")],
        [types.InlineKeyboardButton(text="📊 View on STON.fi", url=f"https://app.ston.fi/swap?ft={jetton_address}")],
        [types.InlineKeyboardButton(text="📊 View on DeDust", url=f"https://dedust.io/swap/{jetton_address}-TON")],
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)


async def get_token_info(jetton_address: str) -> str:
    """Формирует информацию о токене"""
    try:
        metadata = await get_jetton_metadata(jetton_address)
        print(metadata)
        price, price_source = await get_jetton_price(jetton_address)

        if price is not None and price > 0:
            price_text = f"💰 Price: {price:.8f} TON\n📡 Source: {price_source}"
        else:
            price_text = "⚠️ Price not available"

        return (
            f"📛 {metadata['name']} ({metadata['symbol']})\n"
            f"{price_text}\n"
            f"🔢 Decimals: {metadata['decimals']}\n"
            f"📍 Address: {jetton_address}\n"
            f"✅ Verified: {'Yes' if metadata.get('verified') else 'No'}"
        )
    except Exception as e:
        logger.error(f"Error processing {jetton_address}: {e}")
        return f"❌ Error processing token\n📍 {jetton_address}"



@dp.callback_query(lambda c: c.data.startswith("refresh_"))
async def refresh_token_info(callback_query: types.CallbackQuery):
    """Обновление информации о токене по кнопке"""
    address = callback_query.data.split("_", 1)[1]
    info = await get_token_info(address)
    await callback_query.message.edit_text(info, reply_markup=build_token_keyboard(address))
    await callback_query.answer("✅ Data refreshed")


@dp.message(Command("start"))
async def start_handler(message: types.Message):
    await message.answer("👋 Hi! Use /pairs to get jetton tokens info")


@dp.message(Command("pairs"))
async def pairs_handler(message: types.Message):
    try:
        await message.answer("🔄 Loading tokens from database...")

        addresses = await get_jetton_addresses_from_db()
        if not addresses:
            await message.answer("❌ No tokens found in database")
            return

        await message.answer(f"✅ Found {len(addresses)} tokens. Getting info...")

        for symbol, address in addresses.items():
            try:
                info = await get_token_info(address)
                await message.answer(info, reply_markup=build_token_keyboard(address))
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Error with {address}: {e}")
                await message.answer(f"⚠️ Error with token: {address}")

    except Exception as e:
        logger.error(f"Pairs command error: {e}")
        await message.answer("❌ Error processing request")


@dp.message(Command("token"))
async def token_handler(message: types.Message):
    """Check specific token by address"""
    try:
        args = message.text.split()
        if len(args) < 2:
            await message.answer("❌ Usage: /token <jetton_address>")
            return

        address = args[1].strip()
        if not re.match(r'^EQ[0-9A-Za-z_\-]{48}$', address):
            await message.answer("❌ Invalid jetton address format")
            return

        info = await get_token_info(address)
        await message.answer(info, reply_markup=build_token_keyboard(address))

    except Exception as e:
        await message.answer(f"❌ Error: {str(e)}")


@dp.message(Command("help"))
async def help_handler(message: types.Message):
    help_text = """
🤖 Available commands:

/pairs - Show all tokens from database
/token <address> - Check specific token
/help - Show this help

Each token message includes buttons:
🔄 Refresh — update data
📊 View on STON.fi
📊 View on DeDust
"""
    await message.answer(help_text)


async def main():
    logger.info("Starting bot with multi-exchange support + buttons...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
