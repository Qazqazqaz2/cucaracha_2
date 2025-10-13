#!/usr/bin/env python3
"""
Test script to verify token address extraction
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from indexator import extract_addr, _pick_first

# Test cases
test_cases = [
    # Test case 1: Simple string address
    {
        "name": "Simple string address",
        "token_field": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs",
        "expected": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs"
    },
    # Test case 2: Dictionary with address field
    {
        "name": "Dictionary with address field",
        "token_field": {
            "address": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs",
            "symbol": "TON",
            "decimals": 9
        },
        "expected": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs"
    },
    # Test case 3: Dictionary with tokenAddress field
    {
        "name": "Dictionary with tokenAddress field",
        "token_field": {
            "tokenAddress": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs",
            "name": "Toncoin",
            "decimals": 9
        },
        "expected": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs"
    },
    # Test case 4: Dictionary with token_address field
    {
        "name": "Dictionary with token_address field",
        "token_field": {
            "token_address": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs",
            "symbol": "TON",
            "decimals": 9
        },
        "expected": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs"
    },
    # Test case 5: Invalid address format
    {
        "name": "Invalid address format",
        "token_field": "invalid_address",
        "expected": None
    },
    # Test case 6: None value
    {
        "name": "None value",
        "token_field": None,
        "expected": None
    },
    # Test case 7: Dictionary without address fields
    {
        "name": "Dictionary without address fields",
        "token_field": {
            "symbol": "TON",
            "decimals": 9
        },
        "expected": None
    }
]

def test_extract_addr():
    """Test the extract_addr function"""
    print("Testing extract_addr function...")
    passed = 0
    failed = 0
    
    for i, test_case in enumerate(test_cases, 1):
        result = extract_addr(test_case["token_field"])
        expected = test_case["expected"]
        
        if result == expected:
            print(f"  Test {i} ({test_case['name']}): PASSED")
            passed += 1
        else:
            print(f"  Test {i} ({test_case['name']}): FAILED")
            print(f"    Expected: {expected}")
            print(f"    Got: {result}")
            failed += 1
    
    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0

def test_pick_first():
    """Test the _pick_first function"""
    print("\nTesting _pick_first function...")
    
    # Test data
    pool_obj = {
        "token0_address": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs",
        "token1Address": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs2",
        "token_wallet0_address": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs3"
    }
    
    # Test picking token0_address
    result = _pick_first(pool_obj, ["token0_address", "token0Address"])
    expected = "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs"
    
    if result == expected:
        print("  Test 1 (pick token0_address): PASSED")
    else:
        print("  Test 1 (pick token0_address): FAILED")
        print(f"    Expected: {expected}")
        print(f"    Got: {result}")
        return False
    
    # Test picking token1Address
    result = _pick_first(pool_obj, ["token1_address", "token1Address"])
    expected = "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs2"
    
    if result == expected:
        print("  Test 2 (pick token1Address): PASSED")
    else:
        print("  Test 2 (pick token1Address): FAILED")
        print(f"    Expected: {expected}")
        print(f"    Got: {result}")
        return False
    
    print("  All _pick_first tests passed!")
    return True

if __name__ == "__main__":
    print("Running token extraction tests...\n")
    
    success1 = test_extract_addr()
    success2 = test_pick_first()
    
    if success1 and success2:
        print("\nAll tests passed! The token extraction functions are working correctly.")
    else:
        print("\nSome tests failed. Please check the implementation.")