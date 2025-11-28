import asyncio
from pytoniq import WalletV5R1, LiteClient

async def verify_wallet_address():
    # Your mnemonic
    mnemonic = "century stock hero proud immense kick prevent wagon seek myth scare chicken flat seek pass assault spring shed mother income camera rate wine century"
    mnemonic_words = mnemonic.split()
    
    print(f"Mnemonic: {mnemonic}")
    
    # Create lite client
    client = LiteClient.from_mainnet_config(ls_i=1)
    
    try:
        await client.connect()
        print("Connected to mainnet")
        
        # Create wallet from mnemonic
        wallet = await WalletV5R1.from_mnemonic(
            provider=client,
            mnemonics=mnemonic_words,
            wallet_id=2147483409,  # Standard wallet ID
            network_global_id=-239  # Mainnet
        )
        
        # Get different address formats
        bounceable_address = wallet.address.to_str(is_bounceable=True, is_url_safe=True)
        non_bounceable_address = wallet.address.to_str(is_bounceable=False, is_url_safe=True)
        raw_address = wallet.address.to_str(is_bounceable=True, is_url_safe=False)
        
        print(f"Bounceable address (EQ): {bounceable_address}")
        print(f"Non-bounceable address (UQ): {non_bounceable_address}")
        print(f"Raw address: {raw_address}")
        
        # Check which one matches your addresses
        system_address = "EQD1V6ZNou__gvGZ9b-c69g9n1aXvSN4HJG1avp-AHDSRrpO"
        your_address = "UQD1V6ZNou__gvGZ9b-c69g9n1aXvSN4HJG1avp-AHDSRueL"
        
        if bounceable_address == system_address:
            print("✅ The mnemonic generates the system address (EQ format)")
        elif bounceable_address == your_address:
            print("✅ The mnemonic generates your address (EQ format)")
        else:
            print("❌ The mnemonic doesn't generate either address")
            
        if non_bounceable_address == system_address:
            print("✅ The mnemonic generates the system address (UQ format)")
        elif non_bounceable_address == your_address:
            print("✅ The mnemonic generates your address (UQ format)")
        else:
            print("❌ The mnemonic doesn't generate either address")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(verify_wallet_address())