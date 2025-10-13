#!/usr/bin/env python3
"""
Test script to verify that only token addresses are extracted and stored
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from indexator import extract_addr

# Mock connection class for testing
class MockConnection:
    def __init__(self):
        self.executed_queries = []
    
    async def execute(self, query, *args):
        self.executed_queries.append((query, args))
        print(f"Executed query: {query}")
        print(f"With args: {args}")
        return None

# Test cases with different pool object formats
test_cases = [
    {
        "name": "Pool with string token addresses",
        "pool_obj": {
            "pool_address": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs",
            "token0_address": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs1",
            "token1_address": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs2",
            "lp_fee": 30,
            "protocol_fee": 0
        }
    },
    {
        "name": "Pool with token objects containing addresses",
        "pool_obj": {
            "pool_address": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs",
            "token0_address": {
                "address": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs1",
                "symbol": "TON",
                "decimals": 9,
                "name": "Toncoin",
                "other_field": "should_be_ignored"
            },
            "token1_address": {
                "token_address": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs2",
                "symbol": "USDT",
                "decimals": 6,
                "name": "Tether",
                "other_field": "should_be_ignored"
            },
            "lp_fee": 30,
            "protocol_fee": 0
        }
    },
    {
        "name": "Pool with mixed token formats",
        "pool_obj": {
            "address": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs",
            "token0_address": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs1",
            "token1_address": {
                "tokenAddress": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs2",
                "symbol": "USDT",
                "decimals": 6
            },
            "fee": 30,
            "protocolFee": 0
        }
    }
]

async def test_upsert_pool_and_tokens():
    """Test the upsert_pool_and_tokens function"""
    print("Testing upsert_pool_and_tokens function...")
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n  Test {i}: {test_case['name']}")
        pool_obj = test_case['pool_obj']
        
        # Create a mock connection
        mock_conn = MockConnection()
        
        # Import the function here to avoid circular imports
        import asyncio
        import asyncpg
        from indexator import upsert_pool_and_tokens
        
        # Call the function
        try:
            await upsert_pool_and_tokens(mock_conn, pool_obj)
            
            # Check if queries were executed
            if mock_conn.executed_queries:
                print(f"    Result: PASSED - Queries executed successfully")
                
                # Check the first query (pool insertion)
                if mock_conn.executed_queries:
                    query, args = mock_conn.executed_queries[0]
                    pool_addr = args[0] if len(args) > 0 else "N/A"
                    token0_addr = args[1] if len(args) > 1 else "N/A"
                    token1_addr = args[2] if len(args) > 2 else "N/A"
                    
                    print(f"    Pool address: {pool_addr}")
                    print(f"    Token0 address: {token0_addr}")
                    print(f"    Token1 address: {token1_addr}")
                    
                    # Verify that only addresses were extracted (not full objects)
                    if isinstance(token0_addr, str) and len(token0_addr) > 30:
                        print(f"    Token0 correctly extracted as address")
                    else:
                        print(f"    WARNING: Token0 may not be correctly extracted")
                        
                    if isinstance(token1_addr, str) and len(token1_addr) > 30:
                        print(f"    Token1 correctly extracted as address")
                    else:
                        print(f"    WARNING: Token1 may not be correctly extracted")
            else:
                print(f"    Result: FAILED - No queries executed")
                
        except Exception as e:
            print(f"    Result: FAILED - Exception occurred: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    import asyncio
    print("Running database extraction tests...\n")
    asyncio.run(test_upsert_pool_and_tokens())
    print("\nTest completed.")