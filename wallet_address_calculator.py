import base64
import hashlib
import hmac
from mnemonic import Mnemonic
from pytoniq_core import Address, Builder, StateInit
from pytoniq_core.boc import Cell
import secrets

def mnemonic_to_private_key(mnemonic_phrase: str, passphrase: str = "") -> bytes:
    """
    Конвертирует мнемоническую фразу в приватный ключ используя BIP-39
    """
    mnemo = Mnemonic("english")
    
    # Валидация мнемоники
    if not mnemo.check(mnemonic_phrase):
        raise ValueError("Invalid mnemonic phrase")
    
    # Генерируем seed из мнемоники
    seed = mnemo.to_seed(mnemonic_phrase, passphrase)
    
    # Используем первые 32 байта seed как приватный ключ
    private_key = seed[:32]
    
    return private_key

def private_key_to_public_key(private_key: bytes) -> bytes:
    """
    Конвертирует приватный ключ в публичный ключ используя Curve25519
    """
    try:
        from nacl.signing import SigningKey
        # Создаем SigningKey из приватного ключа
        signing_key = SigningKey(private_key)
        # Получаем VerifyKey (публичный ключ)
        verify_key = signing_key.verify_key
        return verify_key.encode()
    except ImportError:
        # Fallback: используем простой HMAC если nacl недоступен
        print("Warning: nacl not available, using fallback key generation")
        return hashlib.sha256(private_key).digest()

def create_wallet_v3_state_init(public_key: bytes, wallet_id: int = 0) -> StateInit:
    """
    Создает StateInit для кошелька v3 (самый распространенный формат)
    """
    # Стандартный код кошелька v3
    wallet_v3_code_hex = "B5EE9C72410101010044000084FF0020DDA4F260810200D71820D70B1FED44D0D31FD3FFD15112BAF2A122F901541044F910F2A2F80001D31F3120D74A96D307D402FB00DED1A4C8CB1FCBFFC9ED5441FDF089"
    
    code_cell = Cell.one_from_boc(base64.b16decode(wallet_v3_code_hex))
    
    # Создаем данные для кошелька
    data_builder = Builder()
    data_builder.store_uint(0, 32)  # seqno
    data_builder.store_bytes(public_key)  # public key
    data_builder.store_uint(wallet_id, 32)  # wallet id
    
    data_cell = data_builder.end_cell()
    
    return StateInit(code=code_cell, data=data_cell)

def create_wallet_v4_state_init(public_key: bytes, wallet_id: int = 0) -> StateInit:
    """
    Создает StateInit для кошелька v4
    """
    # Код кошелька v4
    wallet_v4_code_hex = "B5EE9C724101010100710000DEFF0020DD2082014C97BA9730ED44D0D70B1FE0A4F260810200D71820D70B1FED44D0D31FD3FFD15112BAF2A122F901541044F910F2A2F80001D31F3120D74A96D307D402FB00DED1A4C8CB1FCBFFC9ED54D0E2786F"
    
    code_cell = Cell.one_from_boc(base64.b16decode(wallet_v4_code_hex))
    
    # Создаем данные для кошелька v4
    data_builder = Builder()
    data_builder.store_uint(wallet_id, 32)  # wallet id
    data_builder.store_uint(0, 32)  # seqno
    data_builder.store_bytes(public_key)  # public key
    data_builder.store_uint(0, 1)  # plugins dict empty
    
    data_cell = data_builder.end_cell()
    
    return StateInit(code=code_cell, data=data_cell)

def calculate_wallet_address(mnemonic_phrase: str, wallet_version: str = "v3", wallet_id: int = 0, workchain: int = 0):
    """
    Рассчитывает адрес кошелька из мнемоники
    """
    # Конвертируем мнемонику в приватный ключ
    private_key = mnemonic_to_private_key(mnemonic_phrase)
    print(f"Private key (hex): {private_key.hex()}")
    
    # Получаем публичный ключ
    public_key = private_key_to_public_key(private_key)
    print(f"Public key (hex): {public_key.hex()}")
    
    # Создаем StateInit в зависимости от версии кошелька
    if wallet_version == "v3":
        state_init = create_wallet_v3_state_init(public_key, wallet_id)
    elif wallet_version == "v4":
        state_init = create_wallet_v4_state_init(public_key, wallet_id)
    else:
        raise ValueError(f"Unsupported wallet version: {wallet_version}")
    
    # Получаем адрес
    address = state_init.address(workchain)
    
    return address.to_str(is_bounceable=True, is_url_safe=True)

def try_different_wallet_versions(mnemonic_phrase: str):
    """
    Пробует разные версии кошельков и параметры
    """
    target_address = "EQD1V6ZNou__gvGZ9b-c69g9n1aXvSN4HJG1avp-AHDSRrpO"
    
    print(f"Target address: {target_address}")
    print("Trying different wallet configurations...")
    
    # Пробуем разные версии кошельков
    versions = ["v3", "v4"]
    wallet_ids = [0, 698983191]  # 0 и популярный wallet_id
    
    for version in versions:
        for wallet_id in wallet_ids:
            try:
                address = calculate_wallet_address(mnemonic_phrase, version, wallet_id)
                print(f"Version: {version}, Wallet ID: {wallet_id} -> {address}")
                
                if address == target_address:
                    print(f"✅ MATCH FOUND! Version: {version}, Wallet ID: {wallet_id}")
                    return version, wallet_id, address
            except Exception as e:
                print(f"Error with version {version}, wallet_id {wallet_id}: {e}")
    
    return None, None, None

# Основная функция
if __name__ == "__main__":
    mnemonic = "puzzle eager kit direct brief myth kid smooth spy valve struggle initial enroll champion girl sheriff flip radar always parent engine wing goddess grunt"
    
    print("Calculating wallet address from mnemonic...")
    print(f"Mnemonic: {mnemonic}")
    print()
    
    # Пробуем найти правильную конфигурацию
    version, wallet_id, address = try_different_wallet_versions(mnemonic)
    
    if address:
        print(f"\n✅ Success! Correct configuration:")
        print(f"Wallet version: {version}")
        print(f"Wallet ID: {wallet_id}")
        print(f"Address: {address}")
    else:
        print("\n❌ No matching configuration found")
        print("Trying manual calculation...")
        
        # Покажем адреса для разных версий
        for version in ["v3", "v4"]:
            try:
                addr = calculate_wallet_address(mnemonic, version, 0)
                print(f"{version} (id=0): {addr}")
            except Exception as e:
                print(f"Error with {version}: {e}")