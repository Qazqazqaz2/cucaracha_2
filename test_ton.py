#!/usr/bin/env python3
"""
Simple test script to verify TON library installation
"""

try:
    from pytonlib import TonlibClient
    print("pytonlib imported successfully!")
    
    # Test creating a client
    client = TonlibClient()
    print("TonlibClient created successfully!")
    
except ImportError as e:
    print(f"Failed to import pytonlib: {e}")
    
except Exception as e:
    print(f"Error creating TonlibClient: {e}")

try:
    from ton import TonClient, Wallet, Address
    print("ton library imported successfully!")
    
except ImportError as e:
    print(f"Failed to import ton library: {e}")
    
except Exception as e:
    print(f"Error with ton library: {e}")

print("Test completed.")