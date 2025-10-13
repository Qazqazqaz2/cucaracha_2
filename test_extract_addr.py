#!/usr/bin/env python3
"""
Test script to verify the extract_addr function
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from indexator import extract_addr

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

if __name__ == "__main__":
    print("Running extract_addr tests...\n")
    success = test_extract_addr()
    
    if success:
        print("\nAll tests passed! The extract_addr function is working correctly.")
    else:
        print("\nSome tests failed. Please check the implementation.")