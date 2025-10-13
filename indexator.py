import asyncio
from asyncio import Semaphore
import logging
from typing import Dict, List, Optional
from datetime import datetime, timezone
import aiohttp
import asyncpg
from pytonapi import AsyncTonapi
from pytonapi.exceptions import TONAPIError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("indexer")

STON_POOLS_URL = "https://api.ston.fi/v1/pools"
DEDUST_POOLS_URL = "https://api.dedust.io/v2/pools"
DB_DSN = "postgresql://postgres:762341@localhost:5432/cryptoindexator"
TONAPI_KEY = "AETCLN35NXJY4KYAAAAAKZM7O7ZUUMPOUMTHTWKNUYE7OVPPTE7R3ZNYDU4ZSQYF5BZ36HY"
TON_ADDRESS = "EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c"
STON_API = "https://api.ston.fi/v1"
REFRESH_INTERVAL = 300  # 5 minutes
CONCURRENCY_LIMIT = 10

TONAPI_RATE_LIMIT = 1  # одновременно максимум 1 запрос
tonapi_sem = asyncio.Semaphore(TONAPI_RATE_LIMIT)


async def init_db(dsn: str):
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS jettons (
            id SERIAL PRIMARY KEY,
            address TEXT UNIQUE NOT NULL,
            symbol TEXT,
            name TEXT,
            decimals INTEGER,
            total_supply NUMERIC,
            price_ton FLOAT,
            price_usd FLOAT,
            liquidity FLOAT,
            last_checked TIMESTAMP WITH TIME ZONE DEFAULT now()
        );
        """)
        await conn.execute("ALTER TABLE jettons ADD COLUMN IF NOT EXISTS symbol TEXT;")
        await conn.execute("ALTER TABLE jettons ADD COLUMN IF NOT EXISTS name TEXT;")
        await conn.execute("ALTER TABLE jettons ADD COLUMN IF NOT EXISTS decimals INTEGER;")
        await conn.execute("ALTER TABLE jettons ALTER COLUMN total_supply TYPE NUMERIC USING total_supply::NUMERIC;")
        await conn.execute("ALTER TABLE jettons ADD COLUMN IF NOT EXISTS price_ton FLOAT;")
        await conn.execute("ALTER TABLE jettons ADD COLUMN IF NOT EXISTS price_usd FLOAT;")
        await conn.execute("ALTER TABLE jettons ADD COLUMN IF NOT EXISTS liquidity FLOAT;")
        await conn.execute("ALTER TABLE jettons ADD COLUMN IF NOT EXISTS last_checked TIMESTAMP WITH TIME ZONE DEFAULT now();")

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS pools (
            id SERIAL PRIMARY KEY,
            pool_address TEXT UNIQUE NOT NULL,
            token0_address TEXT NOT NULL,
            token1_address TEXT NOT NULL,
            lp_fee INTEGER,
            protocol_fee INTEGER,
            platform TEXT,
            last_checked TIMESTAMP WITH TIME ZONE DEFAULT now()
        );
        """)
        await conn.execute("ALTER TABLE pools ADD COLUMN IF NOT EXISTS platform TEXT;")

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS pool_reserves (
            id SERIAL PRIMARY KEY,
            pool_id INTEGER REFERENCES pools(id) ON DELETE CASCADE,
            reserve0 NUMERIC,
            reserve1 NUMERIC,
            checked_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        );
        """)
        await conn.execute("ALTER TABLE pools ADD COLUMN IF NOT EXISTS price_per_ton FLOAT;")
        await conn.execute("ALTER TABLE pools ADD COLUMN IF NOT EXISTS lp_total_supply NUMERIC;")
        await conn.execute("ALTER TABLE pools ADD COLUMN IF NOT EXISTS protocol_fee_percent FLOAT;")
        
    finally:
        await conn.close()

async def make_request(url: str, params: dict = None) -> dict:
    """Universal request method"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params or {}) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"API error {response.status} for {url}")
                    return None
    except Exception as e:
        logger.error(f"Request failed: {e}")
        return None

async def limited_tonapi_call(coro):
    """Ограничение скорости запросов TONAPI"""
    async with tonapi_sem:
        try:
            result = await coro
        except TONAPIError as e:
            logger.error(f"TONAPI error: {e}")
            return None
        await asyncio.sleep(1)
        return result


# === БАТЧЕВАЯ ЗАГРУЗКА ЦЕН ===
async def get_jetton_prices_batch(tonapi: AsyncTonapi, addrs: List[str]) -> Dict[str, Dict[str, float]]:
    """Получить цены для нескольких токенов за 1 запрос"""
    prices = {}
    try:
        data = await limited_tonapi_call(tonapi.rates.get_prices(addrs, ["ton", "usd"]))
        if not data:
            return prices

        # Пробуем разные варианты, т.к. структура pytonapi изменилась
        rates_source = getattr(data, "rates", None) or getattr(data, "items", None) or data

        # Конвертируем в dict, если это не словарь
        if not isinstance(rates_source, dict):
            try:
                rates_source = rates_source.model_dump()
            except Exception:
                rates_source = {}

        for addr, info in rates_source.items():
            # info может быть объектом или dict
            if isinstance(info, dict):
                ton_price = info.get("ton") or info.get("TON") or 0
                usd_price = info.get("usd") or info.get("USD") or 0
            else:
                ton_price = getattr(info, "ton", 0)
                usd_price = getattr(info, "usd", 0)
            prices[addr] = {"ton": ton_price or 0, "usd": usd_price or 0}

    except TONAPIError as e:
        logger.error(f"Failed to batch fetch prices: {e}")
    except Exception as e:
        logger.error(f"Unexpected error parsing TONAPI rates: {e}")
    return prices


async def get_jetton_price_and_liquidity(session: aiohttp.ClientSession, tonapi: AsyncTonapi, addr: str):
    """Получить цену токена и ликвидность через TONAPI + STON API"""
    # STON API может вернуть 400, игнорируем это
    liquidity = 0
    try:
        async with session.get(f"{STON_API}/assets/{addr}") as resp:
            if resp.status == 200:
                data = await resp.json()
                liquidity = data.get("liquidity", {}).get("usd", 0)
            else:
                logger.debug(f"STON asset {addr} returned {resp.status}")
    except Exception as e:
        logger.debug(f"STON asset fetch failed for {addr}: {e}")

    # Цена токена через TONAPI
    price_data = await get_jetton_prices_batch(tonapi, [addr])
    token_price = price_data.get(addr, {"ton": 0, "usd": 0})

    return token_price["ton"], token_price["usd"], liquidity


async def fetch_ston_pools(session: aiohttp.ClientSession) -> List[Dict]:
    logger.info("Fetching pools from STON.fi API...")
    pools = []
    async with session.get(STON_POOLS_URL, params={"limit": 1000}) as resp:
        if resp.status != 200:
            logger.error("STON.fi API returned %s", resp.status)
            return pools
        data = await resp.json()
        pools = data.get("pool_list", [])
    logger.info("Fetched %d pools", len(pools))
    return pools

async def fetch_dedust_pools(session: aiohttp.ClientSession) -> List[Dict]:
    logger.info("Fetching pools from DeDust.io API...")
    pools = []
    async with session.get(DEDUST_POOLS_URL, params={"limit": 1000}) as resp:
        if resp.status != 200:
            logger.error("DeDust.io API returned %s", resp.status)
            return pools
        data = await resp.json()
        raw_pools = data if isinstance(data, list) else data.get("pools", [])
        for p in raw_pools:
            asset0 = p["assets"][0]
            asset1 = p["assets"][1]
            token0_address = asset0.get("address", TON_ADDRESS) if asset0["type"] == "jetton" else TON_ADDRESS
            token1_address = asset1.get("address", TON_ADDRESS) if asset1["type"] == "jetton" else TON_ADDRESS
            pool_dict = {
                "address": p["address"],
                "token0_address": token0_address,
                "token1_address": token1_address,
                "lp_fee": int(float(p.get("tradeFee", "0")) * 100),
                "protocol_fee": 0,  # DeDust may not have separate protocol fee
                "platform": "dedust"
            }
            pools.append(pool_dict)
    logger.info("Fetched %d pools from DeDust.io", len(pools))
    return pools

async def upsert_pool_and_tokens(conn: asyncpg.Connection, pool: Dict, tonapi: AsyncTonapi, platform: str, session: aiohttp.ClientSession):
    pool_addr = pool.get("address")
    token0_addr = pool.get("token0_address")
    token1_addr = pool.get("token1_address")
    lp_fee = int(pool.get("lp_fee", 0))
    protocol_fee = int(pool.get("protocol_fee", 0))

    if not all([pool_addr, token0_addr, token1_addr]):
        return

    # Обновляем pool
    await conn.execute("""
    INSERT INTO pools (pool_address, token0_address, token1_address, lp_fee, protocol_fee, platform, last_checked)
    VALUES ($1, $2, $3, $4, $5, $6, NOW())
    ON CONFLICT (pool_address) DO UPDATE SET
        token0_address = EXCLUDED.token0_address,
        token1_address = EXCLUDED.token1_address,
        lp_fee = EXCLUDED.lp_fee,
        protocol_fee = EXCLUDED.protocol_fee,
        platform = EXCLUDED.platform,
        last_checked = NOW()
    """, pool_addr, token0_addr, token1_addr, lp_fee, protocol_fee, platform)

    # Проверяем jettons — фильтруем только те, что требуют обновления
    token_addresses = [a for a in (token0_addr, token1_addr) if a != TON_ADDRESS]
    stale_tokens = []
    for addr in token_addresses:
        exists_recent = await conn.fetchval("""
        SELECT 1 FROM jettons WHERE address = $1 AND last_checked > NOW() - INTERVAL '1 day'
        """, addr)
        if not exists_recent:
            stale_tokens.append(addr)

    if not stale_tokens:
        return

    # Обрабатываем батчами по 10 токенов
    batch_size = 10
    for i in range(0, len(stale_tokens), batch_size):
        batch = stale_tokens[i:i+batch_size]

        # Получаем метаданные
        jetton_infos = []
        for addr in batch:
            info = await limited_tonapi_call(tonapi.jettons.get_info(addr))
            if info:
                jetton_infos.append(info)
            await asyncio.sleep(0.5)  # лёгкий троттлинг

        # Получаем цены для всех за один раз
        price_data = await get_jetton_prices_batch(tonapi, batch)

        # Обновляем каждую запись в БД
        for info in jetton_infos:
            # В некоторых версиях pytonapi адрес лежит в metadata или jetton
            addr = getattr(info, "address", None)
            if not addr:
                addr = getattr(getattr(info, "metadata", {}), "address", None)
            if not addr:
                addr = getattr(getattr(info, "jetton", {}), "address", None)

            if not addr:
                logger.warning(f"JettonInfo без address: {info}")
                continue

            metadata = getattr(info, "metadata", None)
            if not metadata:
                logger.warning(f"JettonInfo без metadata: {addr}")
                continue

            addr_str = str(addr)
            ton_price = price_data.get(addr_str, {}).get("ton", 0)
            usd_price = price_data.get(addr_str, {}).get("usd", 0)
            ston_data = await make_request(f"{STON_API}/assets/{addr}")
            liquidity = ston_data.get("liquidity", {}).get("usd", 0) if ston_data else 0
            if liquidity < 1000:
                continue
            try:
                await conn.execute("""
                INSERT INTO jettons (address, symbol, name, decimals, total_supply, price_ton, price_usd, liquidity, last_checked)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                ON CONFLICT (address) DO UPDATE SET
                    symbol = EXCLUDED.symbol,
                    name = EXCLUDED.name,
                    decimals = EXCLUDED.decimals,
                    total_supply = EXCLUDED.total_supply,
                    price_ton = EXCLUDED.price_ton,
                    price_usd = EXCLUDED.price_usd,
                    liquidity = EXCLUDED.liquidity,
                    last_checked = NOW()
                """, addr, metadata.symbol, metadata.name,
                    int(metadata.decimals) if metadata.decimals else 9,
                    str(info.total_supply),
                    ton_price, usd_price, liquidity)
            except Exception as e:
                logger.error(f"DB upsert failed for {addr}: {e}")

async def fetch_pool_reserves(session: aiohttp.ClientSession, pool: Dict):
    pool_addr = pool["pool_address"]
    platform = pool["platform"]
    
    if platform == "ston":
        url = f"https://api.ston.fi/v1/pools/{pool_addr}"
    elif platform == "dedust":
        url = f"https://api.dedust.io/v2/pools/{pool_addr}"
    else:
        logger.error("Unknown platform for pool %s", pool_addr)
        return None

    async with session.get(url) as resp:
        if resp.status != 200:
            logger.error("Failed to fetch reserves for pool %s (%s)", pool_addr, platform)
            return None
        
        data = await resp.json()
        
        if platform == "ston":
            reserve0 = float(data.get("reserve0", "0"))
            reserve1 = float(data.get("reserve1", "0"))
            lp_total_supply = float(data.get("lp_total_supply", "0"))
        else:  # dedust
            reserves = data.get("reserves", ["0", "0"])
            reserve0 = float(reserves[0])
            reserve1 = float(reserves[1])
            lp_total_supply = float(data.get("total_supply", "0"))
        
        # Calculate TON price based on which token is TON
        token0_addr = pool["token0_address"]
        token1_addr = pool["token1_address"]
        
        price_per_ton = None
        token_symbol = None
        
        if token0_addr == TON_ADDRESS and reserve0 > 0:
            price_per_ton = reserve1 / reserve0  # Price of token1 in TON
            # Get the non-TON token symbol for display
            token_symbol = await get_token_symbol(conn, token1_addr)
        elif token1_addr == TON_ADDRESS and reserve1 > 0:
            price_per_ton = reserve0 / reserve1  # Price of token0 in TON
            token_symbol = await get_token_symbol(conn, token0_addr)
        
        return {
            "pool_id": pool["id"],
            "reserve0": reserve0,
            "reserve1": reserve1,
            "price_per_ton": price_per_ton,
            "lp_total_supply": lp_total_supply,
            "token_symbol": token_symbol,
            "platform": platform
        }

async def get_token_symbol(conn: asyncpg.Connection, token_addr: str) -> str:
    """Get token symbol from database"""
    if token_addr == TON_ADDRESS:
        return "TON"
    
    result = await conn.fetchrow("SELECT symbol FROM jettons WHERE address = $1", token_addr)
    return result["symbol"] if result else "UNKNOWN"

async def update_pool_data(session: aiohttp.ClientSession, conn: asyncpg.Connection, pool_row):
    """Enhanced function to update pool data and filter invalid pairs"""
    
    # Fetch reserves and calculate price
    reserves_data = await fetch_pool_reserves(session, pool_row)
    
    if not reserves_data or reserves_data["price_per_ton"] is None:
        logger.debug(f"Skipping pool {pool_row['pool_address']} - invalid reserves or non-TON pair")
        return None
    
    # Skip if reserves are too low (indicating inactive pool)
    if reserves_data["reserve0"] < 1e-9 or reserves_data["reserve1"] < 1e-9:
        logger.debug(f"Skipping pool {pool_row['pool_address']} - insufficient liquidity")
        return None
    
    # Get protocol fee
    protocol_fee = await get_pool_fees(session, pool_row["pool_address"], pool_row["platform"])
    
    # Update database with calculated price and fees
    await conn.execute("""
    UPDATE pools SET 
        price_per_ton = $1,
        lp_total_supply = $2, 
        protocol_fee_percent = $3,
        last_checked = NOW()
    WHERE id = $4
    """, reserves_data["price_per_ton"], reserves_data["lp_total_supply"], 
        protocol_fee, pool_row["id"])
    
    # Update pool_reserves table
    await conn.execute("""
    INSERT INTO pool_reserves (pool_id, reserve0, reserve1, checked_at)
    VALUES ($1, $2, $3, NOW())
    """, pool_row["id"], reserves_data["reserve0"], reserves_data["reserve1"])
    
    return reserves_data

async def get_pool_fees(session: aiohttp.ClientSession, pool_addr: str, platform: str):
    """Get protocol fees for a pool"""
    if platform == "ston":
        # STON.fi has fixed protocol fee structure
        return 0.1  # 0.1%
    elif platform == "dedust":
        # Query DeDust pool for fee details
        url = f"https://api.dedust.io/v2/pools/{pool_addr}"
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                # DeDust returns trade_fee_numerator and trade_fee_denominator
                trade_fee_num = data.get("trade_fee_numerator", 0)
                trade_fee_denom = data.get("trade_fee_denominator", 10000)
                return (trade_fee_num / trade_fee_denom) * 100  # Convert to percentage
    return 0.0

async def fetch_candles_for_pool(
    session: aiohttp.ClientSession,
    pool: dict,
    platform: str = "stonfi",
    base_addr: Optional[str] = None,
    quote_addr: Optional[str] = None
) -> dict:
    """Получить процентные изменения цены для пула за 10m/1h/24h/7d/30d."""
    periods = {
        "10m": 10 * 60,
        "1h": 60 * 60,
        "24h": 24 * 60 * 60,
        "7d": 7 * 24 * 60 * 60,
        "30d": 30 * 24 * 60 * 60,
    }
    changes = {}
    now = int(datetime.now(timezone.utc).timestamp())
    try:
        if platform == "stonfi":
            if not (base_addr and quote_addr):
                base_addr = pool["token0_address"]
                quote_addr = pool["token1_address"]
            url = f"https://api.ston.fi/v1/pairs/{base_addr}/{quote_addr}/candles"
            async with session.get(url, params={"interval": "5m", "limit": 650}) as resp:
                if resp.status != 200:
                    logger.warning(f"STON.fi candles returned {resp.status}")
                    return changes
                data = await resp.json()
                candles = data.get("candles", [])
        elif platform == "dedust":
            pool_addr = pool.get("address") or pool.get("pool_address")
            url = f"https://api.dedust.io/v2/pools/{pool_addr}/candles"
            async with session.get(url, params={"interval": "5m", "limit": 650}) as resp:
                if resp.status != 200:
                    logger.warning(f"DeDust.io candles returned {resp.status}")
                    return changes
                data = await resp.json()
                candles = data if isinstance(data, list) else data.get("candles", [])
        else:
            return changes

        # normalized, сортируем по времени
        candles.sort(key=lambda x: x["timestamp"])
        price0 = candles[-1]["close"] if candles else None
        ts0 = candles[-1]["timestamp"] if candles else None
        for label, offset in periods.items():
            past_ts = now - offset
            # ищем candle наиболее близкую к timestamp
            past_candle = min(candles, key=lambda x: abs(x["timestamp"] - past_ts), default=None)
            if past_candle and price0 and past_candle["close"]:
                change = (price0 - past_candle["close"]) / past_candle["close"] * 100
                changes[label] = round(change, 2)
            else:
                changes[label] = None
    except Exception as e:
        logger.error(f"Failed to fetch candles for pool {platform}: {e}")
    return changes


async def run_indexer():
    await init_db(DB_DSN)
    tonapi = AsyncTonapi(account_id=None, api_key=TONAPI_KEY)
    
    async with aiohttp.ClientSession() as session:
        while True:
            conn = await asyncpg.connect(DB_DSN)
            try:
                # Fetch and process STON pools
                ston_pools = await fetch_ston_pools(session)
                for pool in ston_pools:
                    if pool.get("token0_address") == TON_ADDRESS or pool.get("token1_address") == TON_ADDRESS:
                        await upsert_pool_and_tokens(conn, pool, tonapi, "ston", session)

                # Fetch and process DeDust pools  
                dedust_pools = await fetch_dedust_pools(session)
                for pool in dedust_pools:
                    if pool.get("token0_address") == TON_ADDRESS or pool.get("token1_address") == TON_ADDRESS:
                        await upsert_pool_and_tokens(conn, pool, tonapi, "dedust", session)

                # Process pool reserves and prices
                pool_rows = await conn.fetch("""
                SELECT id, pool_address, token0_address, token1_address, platform
                FROM pools 
                WHERE (token0_address = $1 OR token1_address = $1)
                AND last_checked < NOW() - INTERVAL '5 minutes'
                ORDER BY last_checked ASC
                LIMIT 50
                """, TON_ADDRESS)
                
                valid_pools = []
                for pool_row in pool_rows:
                    pool_data = await update_pool_data(session, conn, dict(pool_row))
                    if pool_data and pool_data["price_per_ton"] is not None:
                        valid_pools.append(pool_data)
                
                logger.info(f"Processed {len(valid_pools)} valid pools, filtered out {len(pool_rows) - len(valid_pools)} invalid pairs")

            except Exception as e:
                logger.exception("Indexer error: %s", e)
            finally:
                await conn.close()
            await asyncio.sleep(REFRESH_INTERVAL)

if __name__ == "__main__":
    asyncio.run(run_indexer())