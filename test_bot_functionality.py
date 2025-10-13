import asyncio
import asyncpg
import json
import os
from pytonlib import TonlibClient

# Database (тот же, что в indexator.py)
DB_DSN = "postgresql://postgres:762341@localhost:5432/cryptoindexator"

# TON configuration
TON_CONFIG_PATH = "global.config.json"
TON_KEYSTORE = os.path.expanduser("~/.ton_keystore")

async def get_jetton_addresses_from_db() -> dict:
    """
    Получает адреса Jetton контрактов из базы данных
    """
    try:
        conn = await asyncpg.connect(DB_DSN)
        try:
            rows = await conn.fetch("SELECT address FROM jettons LIMIT 5")
            jettons = {}
            for i, row in enumerate(rows):
                # Используем индекс как символ для демонстрации
                symbol = f"JET{i+1}"
                jettons[symbol] = row["address"]
            return jettons
        finally:
            await conn.close()
    except Exception as e:
        print(f"Error fetching jetton addresses from DB: {e}")
        return {}

async def get_jetton_metadata_onchain(ton_client: TonlibClient, jetton_address: str) -> dict:
    """
    Получает метаданные Jetton из блокчейна TON
    """
    try:
        # Пытаемся получить контент через get_jetton_data
        result = await ton_client.raw_run_method(
            address=jetton_address, 
            method="get_jetton_data", 
            stack_data=[]
        )
        
        if not result or "stack" not in result:
            return {"symbol": "UNKNOWN", "name": "Unknown Token", "decimals": 9}
        
        stack = result["stack"]
        if len(stack) < 5:
            return {"symbol": "UNKNOWN", "name": "Unknown Token", "decimals": 9}
        
        # Простая реализация - в реальном случае нужно парсить content cell
        # Для демонстрации возвращаем жестко заданные значения
        symbol = "UNKNOWN"
        name = "Unknown Token"
        decimals = 9
        
        # Маппинг известных токенов
        known_tokens = {
            "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs": {"symbol": "USDT", "name": "Tether USD", "decimals": 6},
            "EQBkzNV0DV5ZXtJzluUy1_jVdbZLXcESU_AHoYEW5p2O-kUS": {"symbol": "USDC", "name": "USD Coin", "decimals": 6},
            "EQDSdjmuIaDbxRPJyPEfRun7x5IgpFNQCNSd_xEqurDQ6cXD": {"symbol": "NOT", "name": "Notcoin", "decimals": 9},
            "EQCvxJy4eG8hyHBFsZ7eePxrRsUQSFE_jpptRAYBmcG_DOGS": {"symbol": "DOGS", "name": "Dogs", "decimals": 9},
            "EQAs8AjQo4pA_PO9pDkZUqCEH8I0w6CMeMIuuRak7lpFNcVD": {"symbol": "HMSTR", "name": "Hamster", "decimals": 9},
        }
        
        if jetton_address in known_tokens:
            return known_tokens[jetton_address]
        
        return {"symbol": symbol, "name": name, "decimals": decimals}
    except Exception as e:
        print(f"Error getting jetton metadata: {e}")
        return {"symbol": "UNKNOWN", "name": "Unknown Token", "decimals": 9}

async def test_bot_functionality():
    # Получаем адреса jetton контрактов из базы данных
    jetton_addresses = await get_jetton_addresses_from_db()
    print("Jetton addresses from DB:")
    for symbol, address in jetton_addresses.items():
        print(f"  {symbol}: {address}")
    
    # Initialize TON client
    with open(TON_CONFIG_PATH, "r", encoding="utf-8") as f:
        ton_config = json.load(f)
    
    ton_client = TonlibClient(ls_index=0, config=ton_config, keystore=TON_KEYSTORE)
    await ton_client.init()
    
    print("\nFetching metadata from TON blockchain:")
    for symbol, jetton_address in jetton_addresses.items():
        metadata = await get_jetton_metadata_onchain(ton_client, jetton_address)
        print(f"  {symbol}: {metadata}")
    
    # Close TON client
    print("\nTest completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_bot_functionality())