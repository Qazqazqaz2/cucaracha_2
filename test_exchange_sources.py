import asyncio
import aiohttp
import re

def convert_to_raw_address(user_friendly_addr: str) -> str:
    """Конвертирует адрес в raw format"""
    if user_friendly_addr.startswith('EQ'):
        return user_friendly_addr[2:]  # Убираем 'EQ'
    return user_friendly_addr

async def get_jetton_metadata_from_stonfi(jetton_address: str) -> dict:
    """Получает метаданные из STON.fi"""
    try:
        raw_addr = convert_to_raw_address(jetton_address)
        url = f"https://api.ston.fi/v1/tokens/{raw_addr}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "symbol": data.get('symbol', 'UNKNOWN'),
                        "name": data.get('name', 'Unknown Token'),
                        "decimals": data.get('decimals', 9),
                        "description": data.get('description', ''),
                        "verified": data.get('verified', False)
                    }
    except Exception as e:
        print(f"STON.fi error for {jetton_address}: {e}")
    return None

async def get_jetton_metadata_from_dedust(jetton_address: str) -> dict:
    """Получает метаданные из DeDust.io"""
    try:
        raw_addr = convert_to_raw_address(jetton_address)
        # DeDust API для получения информации о токене
        url = f"https://api.dedust.io/v2/assets"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    # Ищем токен в списке активов
                    for asset in data:
                        if asset.get('address') == raw_addr or asset.get('address') == jetton_address:
                            return {
                                "symbol": asset.get('symbol', 'UNKNOWN'),
                                "name": asset.get('name', 'Unknown Token'),
                                "decimals": asset.get('decimals', 9),
                                "description": asset.get('description', ''),
                                "verified": True  # DeDust assets are generally verified
                            }
    except Exception as e:
        print(f"DeDust.io error for {jetton_address}: {e}")
    return None

async def get_all_metadata_sources(jetton_address: str) -> dict:
    """Получает метаданные из всех источников"""
    sources = {}
    
    # Получаем из STON.fi
    stonfi_metadata = await get_jetton_metadata_from_stonfi(jetton_address)
    if stonfi_metadata and stonfi_metadata['symbol'] != 'UNKNOWN':
        sources['stonfi'] = stonfi_metadata
    
    # Получаем из DeDust.io
    dedust_metadata = await get_jetton_metadata_from_dedust(jetton_address)
    if dedust_metadata and dedust_metadata['symbol'] != 'UNKNOWN':
        sources['dedust'] = dedust_metadata
    
    return sources

async def test_multi_exchange_functionality():
    """Test the multi-exchange functionality"""
    # Используем тестовый адрес USDT
    test_address = "EQD26zcd6Cqpz7WyLKVH8x_cD6D7tBrom6hKcycv8L8hV0GP"  # USDT
    
    print(f"Testing multi-exchange functionality for address: {test_address}")
    
    # Получаем метаданные из всех источников
    sources = await get_all_metadata_sources(test_address)
    
    print(f"\nFound metadata from {len(sources)} sources:")
    for source, metadata in sources.items():
        print(f"\n{source.upper()}:")
        print(f"  Symbol: {metadata['symbol']}")
        print(f"  Name: {metadata['name']}")
        print(f"  Decimals: {metadata['decimals']}")
        print(f"  Verified: {metadata['verified']}")
    
    if len(sources) > 1:
        print(f"\n✅ Token found on multiple exchanges. User would be prompted to choose.")
    else:
        print(f"\nℹ️  Token found on {len(sources)} exchange(s).")

if __name__ == "__main__":
    asyncio.run(test_multi_exchange_functionality())