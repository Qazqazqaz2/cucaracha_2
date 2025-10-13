#!/usr/bin/env python3
"""
Simple working example for TON integration
"""

import asyncio
import json
import os
from pytonlib import TonlibClient

# TON configuration
TON_CONFIG_PATH = "global.config.json"
TON_KEYSTORE = os.path.expanduser("~/.ton_keystore")

async def test_ton_client():
    # Initialize TON client
    with open(TON_CONFIG_PATH, "r", encoding="utf-8") as f:
        ton_config = json.load(f)
    
    print("Initializing TON client...")
    ton_client = TonlibClient(ls_index=0, config=ton_config, keystore=TON_KEYSTORE)
    await ton_client.init()
    print("TON client initialized successfully!")
    
    # Test with a known contract address
    try:
        print("Testing with a known contract...")
        result = await ton_client.raw_run_method(
            address="EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs",  # USDT
            method="get_jetton_data", 
            stack_data=[]
        )
        print(f"Result: {result}")
    except Exception as e:
        print(f"Error calling get_jetton_data: {e}")
    
    print("Test completed.")

if __name__ == "__main__":
    asyncio.run(test_ton_client())
