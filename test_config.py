try:
    from config import TELEGRAM_TOKEN, TRADING_CONFIG
    print("SUCCESS: Config imported")
    print(f"Token: {TELEGRAM_TOKEN[:10]}...")
    print(f"Wallet: {TRADING_CONFIG.get('wallet_address', 'None')[:15]}...")
except ImportError as e:
    print(f"IMPORT ERROR: {e}")
except Exception as e:
    print(f"OTHER ERROR: {e}")
