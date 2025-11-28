import asyncio
from pytoniq import LiteClient

async def connect_with_retry(client, max_retries=5):
    """
    Connect to client with retry logic
    """
    for attempt in range(max_retries):
        try:
            # Try to connect with proper parameters
            await client.connect()
            print(f"[NETWORK] Successfully connected to network (attempt {attempt + 1})")
            return True
        except Exception as e:
            print(f"[NETWORK] Connection attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                print(f"[NETWORK] All connection attempts failed")
                return False
    return False

def create_lite_client(testnet=False):
    """
    Create LiteClient with proper configuration
    """
    try:
        if testnet:
            # Try different configurations for testnet
            configs = [
                lambda: LiteClient.from_testnet_config(ls_i=1),
                lambda: LiteClient.from_testnet_config(ls_i=0),
                lambda: LiteClient.from_testnet_config(trust_level=1, ls_i=1),
            ]
        else:
            # Try different configurations for mainnet
            configs = [
                lambda: LiteClient.from_mainnet_config(ls_i=1),
                lambda: LiteClient.from_mainnet_config(ls_i=0),
                lambda: LiteClient.from_mainnet_config(trust_level=1, ls_i=1),
            ]
        
        # Try each configuration
        for i, config_func in enumerate(configs):
            try:
                client = config_func()
                return client
            except Exception as e:
                print(f"[NETWORK] Config attempt {i+1} failed: {e}")
                continue
        
        # If all fail, try the default
        if testnet:
            return LiteClient.from_testnet_config()
        else:
            return LiteClient.from_mainnet_config()
            
    except Exception as e:
        print(f"[NETWORK] Failed to create LiteClient: {e}")
        return None