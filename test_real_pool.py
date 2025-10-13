#!/usr/bin/env python3
"""
Test script to verify token address extraction with real pool data
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from indexator import extract_addr, _pick_first

# Example real pool data from STON API (simulated)
real_pool_examples = [
    {
        "name": "Pool with string token addresses",
        "pool_data": {
            "pool_address": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs",
            "token0_address": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs1",
            "token1_address": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs2",
            "lp_fee": 30,
            "protocol_fee": 0
        }
    },
    {
        "name": "Pool with token objects",
        "pool_data": {
            "pool_address": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs",
            "token0": {
                "address": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs1",
                "symbol": "TON",
                "decimals": 9
            },
            "token1": {
                "address": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs2",
                "symbol": "USDT",
                "decimals": 6
            },
            "lp_fee": 30,
            "protocol_fee": 0
        }
    },
    {
        "name": "Pool with mixed token formats",
        "pool_data": {
            "pool_address": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs",
            "token0Address": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs1",
            "token1": {
                "token_address": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs2",
                "symbol": "USDT",
                "decimals": 6
            },
            "lp_fee": 30,
            "protocol_fee": 0
        }
    }
]

def test_real_pool_data():
    """Test token extraction with real pool data"""
    print("Testing token extraction with real pool data...")
    
    for i, example in enumerate(real_pool_examples, 1):
        print(f"\n  Test {i}: {example['name']}")
        pool_data = example['pool_data']
        
        # Extract token0
        token0_raw = _pick_first(pool_data, [
            "token0_address", "token0Address", "token0_wallet_address", "token0WalletAddress",
            "token0", "token_wallet0_address", "token0_wallet"
        ])
        
        token0_address = extract_addr(token0_raw)
        
        # Extract token1
        token1_raw = _pick_first(pool_data, [
            "token1_address", "token1Address", "token1_wallet_address", "token1WalletAddress",
            "token1", "token_wallet1_address", "token1_wallet"
        ])
        
        token1_address = extract_addr(token1_raw)
        
        # Extract pool address
        pool_addr = _pick_first(pool_data, ["pool_address", "poolAddress", "address", "pool"])
        
        print(f"    Pool address: {pool_addr}")
        print(f"    Token0 raw: {token0_raw}")
        print(f"    Token0 address: {token0_address}")
        print(f"    Token1 raw: {token1_raw}")
        print(f"    Token1 address: {token1_address}")
        
        # Validate results
        if pool_addr and token0_address and token1_address:
            print(f"    Result: PASSED - All addresses extracted successfully")
        else:
            print(f"    Result: FAILED - Missing addresses")
            if not pool_addr:
                print(f"      Missing pool address")
            if not token0_address:
                print(f"      Missing token0 address")
            if not token1_address:
                print(f"      Missing token1 address")

if __name__ == "__main__":
    print("Running real pool data tests...\n")
    test_real_pool_data()
    print("\nTest completed.")