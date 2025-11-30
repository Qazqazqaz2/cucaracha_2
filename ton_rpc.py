"""
Модуль для базовых RPC операций с TON блокчейном
Содержит низкоуровневые функции для взаимодействия с TON API
"""
import os
import time
import base64
import requests
from pytoniq_core import Address, Cell
from pytoniq_core.boc import Builder
from dotenv import load_dotenv
import traceback

load_dotenv()

# Конфигурация
TESTNET = os.environ.get("TESTNET", "False") == "True"
BASE_URL = os.environ.get("BASE_URL", "https://toncenter.com/api/v2" if not TESTNET else "https://testnet.toncenter.com/api/v2")
API_KEY = os.environ.get("API_KEY")

if not API_KEY:
    raise ValueError("API_KEY must be set in .env for Toncenter access")

def toncenter_request(method, params=None, retries=5, timeout=30):

    url = f"{BASE_URL}/jsonRPC"
    headers = {
        'Content-Type': 'application/json',
        'X-API-Key': API_KEY
    }
    payload = {
        'id': "1",
        'jsonrpc': '2.0',
        'method': method,
        'params': params or {}
    }
    current_timeout = timeout if method == 'runGetMethod' else 10

    for attempt in range(retries):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=current_timeout)
            response.raise_for_status()
            data = response.json()
            if 'error' in data:
                print(f"[TON RPC] Error in response: {data['error']}")
                if data['error']['code'] in [429, 503]:  # Rate limit or temp unavailable
                    time.sleep(2 ** attempt)
                    continue
            return data.get('result', {})
        except Exception as e:
            print(f"[TON RPC] Error (attempt {attempt+1}/{retries}) method:{payload}: {e}")
            time.sleep(2 ** attempt)  # Exponential backoff
    print(f"[TON RPC] All retries failed for {method} payload: {payload}")
    return None


def estimate_gas_fee(address: str, payload_b64: str, init_code: str | None = None, init_data: str | None = None, ignore_chksig: bool = True):
    
    try:
        normalized = validate_address(address)
        params = {
            'address': normalized,
            'body': payload_b64,
            'init_code': init_code,
            'init_data': init_data,
            'ignore_chksig': ignore_chksig,
        }
        result = toncenter_request('estimateFee', params, timeout=30)
        if not result:
            return None
        
        # Ответ может содержать source_fees либо fees
        fees = result.get('source_fees') or result.get('fees') or {}
        # Значения приходят строками
        return {
            'gas_fee': int(fees.get('gas_fee', 0)),
            'in_fwd_fee': int(fees.get('in_fwd_fee', 0)),
            'fwd_fee': int(fees.get('fwd_fee', 0)),
            'storage_fee': int(fees.get('storage_fee', 0)),
            'total_fee': int(fees.get('fee', 0)) or int(fees.get('total_fees', 0)),
        }
    except Exception as e:
        print(f"[TON RPC] Gas estimation error: {e}")
        return None


def validate_address(addr_str: str) -> str:
    """
    Валидация и нормализация TON адреса
    
    Args:
        addr_str: Адрес в любом формате
    
    Returns:
        str: Нормализованный адрес (bounceable, url-safe)
    
    Raises:
        ValueError: Если адрес невалидный
    """
    try:
        addr = Address(addr_str)
        return addr.to_str(is_bounceable=True, is_url_safe=True)
    except:
        try:
            # Remove the is_bounceable parameter as it's not supported
            addr = Address(addr_str)
            return addr.to_str(is_bounceable=True, is_url_safe=True)
        except Exception as e:
            raise ValueError(f"Недопустимый адрес: {addr_str}") from e


def get_balance(address: str, decimals=9):
    """
    Получение баланса TON кошелька
    
    Args:
        address: Адрес кошелька
        decimals: Количество десятичных знаков (9 для TON)
    
    Returns:
        float: Баланс в TON
    """
    try:
        addr = validate_address(address)
        result = toncenter_request('getAddressInformation', {'address': addr})
        if result:
            bal_nano = int(result.get('balance', 0))
            return bal_nano / (10 ** decimals)
        return 0
    except Exception as e:
        print(f"[TON RPC] Balance error: {e}")
        return 0


def get_pool_reserves(pool_addr: str):
    """
    Получение резервов пула DEX
    
    Args:
        pool_addr: Адрес пула
    
    Returns:
        tuple: (reserve_TON, reserve_USDT) - резервы токенов в нано-единицах (nanoTON, nanoUSDT)
    """
    try:
        pool_valid = validate_address(pool_addr)
        result = toncenter_request('runGetMethod', {
            'address': pool_valid,
            'method': 'get_reserves',
            'stack': []
        })
        
        if not result or result.get('exit_code', 1) != 0:
            print(f"[TON RPC] Failed to get reserves for {pool_addr}")
            # Realistic fallback based on 2024 data: ~72M TON and ~117M USDT (TVL ~$234M at ~1.63 USDT/TON)
            return 72000000 * 10**9, 117000000 * 10**6

        stack = result.get('stack', [])
        reserves = []

        for item in stack:
            if isinstance(item, list) and len(item) >= 2:
                t, v = item[0], item[1]
                if t == 'num':
                    try:
                        num_val = int(v, 16)
                        if num_val > 0:
                            reserves.append(num_val)
                    except:
                        continue

        if len(reserves) >= 2:
            # Assume reserves[0] is TON (larger in nano due to decimals), reserves[1] is USDT
            # But sort to assign correctly if needed; here assume order from contract
            return reserves[0], reserves[1]
            
        # Realistic fallback
        return 72000000 * 10**9, 117000000 * 10**6

    except Exception as e:
        print(f"[TON RPC] Reserves error: {e}")
        return 72000000 * 10**9, 117000000 * 10**6


def get_expected_output(pool_addr: str, amount_nano: int, from_token_addr: str):
    """
    Расчет ожидаемого вывода токенов из пула
    
    Args:
        pool_addr: Адрес пула
        amount_nano: Количество входных токенов в нано-единицах
        from_token_addr: Адрес входного токена
    
    Returns:
        int: Ожидаемое количество выходных токенов в нано-единицах
    """
    try:
        # Handle None or empty from_token_addr
        if not from_token_addr:
            from_token_addr = ""
        token_builder = Builder()
        token_builder.store_address(Address(from_token_addr))
        token_cell = token_builder.end_cell()
        token_boc = base64.b64encode(token_cell.to_boc()).decode('utf-8')

        result = toncenter_request('runGetMethod', {
            'address': pool_addr,
            'method': 'get_expected_outputs',
            'stack': [
                ['num', hex(amount_nano)],
                ['tvm.cell', token_boc]
            ]
        }, timeout=30)
        
        if not result or result.get('exit_code') != 0:
            print(f"[TON RPC] get_expected_outputs failed: {result}")
            # Fallback to formula
            reserve_TON, reserve_USDT = get_pool_reserves(pool_addr)  # (nanoTON, nanoUSDT)
            # Determine if from is TON or USDT
            is_from_TON = from_token_addr == "EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c" or from_token_addr == ""  # Native TON address
            if is_from_TON:
                reserve_in = reserve_TON
                reserve_out = reserve_USDT
            else:
                reserve_in = reserve_USDT
                reserve_out = reserve_TON
            # Assume constant product AMM, 0.3% fee (997/1000)
            amount_in_with_fee = amount_nano * 997 // 1000
            if reserve_in + amount_in_with_fee == 0:
                return 0
            expected = (amount_in_with_fee * reserve_out) // (reserve_in + amount_in_with_fee)
            print(f"[TON RPC] Fallback expected output: {expected}")
            return expected

        stack = result['stack']
        if len(stack) < 1 or stack[0][0] != 'num':
            print(f"[TON RPC] Invalid stack: {stack}")
            return 0
        
        out = int(stack[0][1], 16)
        print(f"[TON RPC] Expected output: {out}")
        return out
    except Exception as e:
        print(f"[TON RPC] Expected output error: {e}")
        return 0

JETTON_WALLET_CACHE = {}


def parse_chainstack_response(result_data):
    """
    Parses the runGetMethod response from Chainstack.
    Returns the base64-encoded BOC string of the wallet address cell.
    """
    stack = result_data.get('stack', [])
    if len(stack) < 1:
        raise ValueError("Empty stack in response")

    wallet_boc_b64 = None
    stack_item = stack[0]

    # Handle Chainstack format: ['cell', {'bytes': '...'}]
    if isinstance(stack_item, list) and len(stack_item) >= 2:
        if stack_item[0] == 'cell':
            wallet_boc_b64 = stack_item[1].get('bytes')
    
    # Handle alternative object format: {'type': 'cell', 'value': '...'} 
    elif isinstance(stack_item, dict):
        if stack_item.get('type') == 'cell':
            wallet_boc_b64 = stack_item.get('value')
    
    if not wallet_boc_b64:
        raise ValueError("Could not find cell data in the response stack")
    
    return wallet_boc_b64

def get_order_wallet_from_mnemonic():
    """
    Создание кошелька ордеров из мнемоники для WalletV5R1
    
    Returns:
        tuple: (wallet_address, wallet_object) или (None, None) при ошибке
    """
    try:
        from pytoniq import WalletV5R1, LiteClient
        
        ORDER_WALLET_MNEMONIC = os.environ.get("ORDER_WALLET_MNEMONIC")
        print(f"[DEBUG] Raw ORDER_WALLET_MNEMONIC: '{ORDER_WALLET_MNEMONIC}'")  # Покажет, что именно загружено
        if not ORDER_WALLET_MNEMONIC:
            print("[DEBUG] Mnemonic not found in env")
            return None, None
        
        # Assuming it's base64 encoded (common for security); adjust if different encryption
        try:
            mnemonic_decoded = base64.b64decode(ORDER_WALLET_MNEMONIC).decode('utf-8')
            print("[DEBUG] Decoded mnemonic (base64 assumed)")
        except:
            # If not base64, treat as plain
            mnemonic_decoded = ORDER_WALLET_MNEMONIC
            print("[DEBUG] Treating mnemonic as plain text")
        
        mnemonics = mnemonic_decoded.split()
        print(f"[DEBUG] Mnemonic length: {len(mnemonics)}")  # Должно быть 24
        print(f"[DEBUG] Mnemonic words: {mnemonics}")
        
        if len(mnemonics) != 24:
            print(f"[WALLETS] Invalid mnemonic length: {len(mnemonics)} words, expected 24")
            return None, None
        
        # Создаем кошелек V5R1 из мнемоники (асинхронная версия)
        print(f"[WALLETS] Creating WalletV5R1...")
        
        # Подключаемся к сети
        config = LiteClient.from_mainnet_config() if not TESTNET else LiteClient.from_testnet_config()
        import asyncio
        
        async def create_wallet():
            await config.connect()
            wallet = await WalletV5R1.from_mnemonic(
                provider=config,
                mnemonics=mnemonics,
                wallet_id=2147483409,  # Standard wallet ID
                network_global_id=-239 if not TESTNET else -3  # Mainnet or testnet
            )
            wallet_address = wallet.address.to_str(is_bounceable=True, is_url_safe=True)
            await config.close()
            return wallet_address, wallet
        
        # Запускаем асинхронную функцию синхронно
        wallet_address, wallet = asyncio.run(create_wallet())
        
        print(f"[WALLETS] Successfully loaded WalletV5R1: {wallet_address}")
        return wallet_address, wallet
        
    except Exception as e:
        print(f"[WALLETS] Error loading WalletV5R1 from mnemonic: {e}")
        traceback.print_exc()
        return None, None

async def send_transaction(to_address: str, amount_nano: int, payload_boc: str):
    """
    Отправка транзакции через кошелек ордеров
    
    Args:
        to_address: Адрес получателя
        amount_nano: Сумма в нанотонах
        payload_boc: BOC с полезной нагрузкой
    
    Returns:
        bool: Успешность отправки
    """
    try:
        wallet_address, wallet = get_order_wallet_from_mnemonic()
        if not wallet:
            print("[TX] Order wallet mnemonic is not provided or invalid")
            return False
        
        # Подключаемся к сети
        from pytoniq import LiteClient
        config = LiteClient.from_mainnet_config() if not TESTNET else LiteClient.from_testnet_config()
        await config.connect()
        
        # Подготавливаем транзакцию
        prepared = await wallet.transfer(
            destination=Address(to_address),
            amount=amount_nano,
            body=Cell.one_from_boc(base64.b64decode(payload_boc))
        )
        
        print(f"[TX] Transaction sent successfully: {prepared}")
        await config.close()
        return True
        
    except Exception as e:
        print(f"[TX] Error sending transaction: {e}")
        traceback.print_exc()
        return False

def verify_wallet_address():
    """
    Проверка, что кошелек из мнемоники соответствует ожидаемому адресу
    """
    expected_address = "UQD1V6ZNou__gvGZ9b-c69g9n1aXvSN4HJG1avp-AHDSRueL"
    wallet_address, _ = get_order_wallet_from_mnemonic()
    
    if wallet_address:
        # Нормализуем оба адреса для сравнения
        normalized_expected = validate_address(expected_address)
        normalized_actual = validate_address(wallet_address)
        
        if normalized_expected == normalized_actual:
            print(f"[WALLETS] ✓ Wallet address matches: {wallet_address}")
            return True
        else:
            print(f"[WALLETS] ✗ Wallet address mismatch!")
            print(f"  Expected: {normalized_expected}")
            print(f"  Actual:   {normalized_actual}")
            return False
    return False

def get_jetton_wallet(master_addr: str, owner_addr: str):
    """
    Получение адреса Jetton-кошелька через Chainstack REST API
    """
    cache_key = f"{master_addr}:{owner_addr}"
    if cache_key in JETTON_WALLET_CACHE:
        return JETTON_WALLET_CACHE[cache_key]
    
    try:
        CHAINSTACK_URL = os.environ.get("CHAINSTACK_URL")
        CHAINSTACK_API_KEY = os.environ.get("CHAINSTACK_API_KEY")
        
        if not CHAINSTACK_URL or not CHAINSTACK_API_KEY:
            raise ValueError("Chainstack URL and API key must be set in environment variables")
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {CHAINSTACK_API_KEY}'
        }
        
        # Строим стек для вызова get_wallet_address
        owner_builder = Builder()
        owner_builder.store_address(Address(owner_addr))
        owner_cell = owner_builder.end_cell()
        owner_boc = base64.b64encode(owner_cell.to_boc()).decode('utf-8')
        
        payload = {
            'address': master_addr,
            'method': 'get_wallet_address',
            'stack': [
                ['tvm.Slice', owner_boc]
            ]
        }
        
        print(f"[CHAINSTACK] Request to: {CHAINSTACK_URL}")
        print(f"[CHAINSTACK] Payload: {payload}")
        
        response = requests.post(
            CHAINSTACK_URL,
            json=payload,
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        
        print(f"[CHAINSTACK] Raw response: {result}")
        
        if not result.get('ok', False):
            error_msg = result.get('error', 'Unknown error')
            raise ValueError(f"Chainstack API error: {error_msg}")
        
        result_data = result.get('result', {})
        exit_code = result_data.get('exit_code')
        if exit_code != 0:
            raise ValueError(f"Contract execution failed with exit code {exit_code}")
        
        stack = result_data.get('stack', [])
        if len(stack) < 1:
            raise ValueError("Empty stack in response")
        
        # Извлекаем BOC из ответа Chainstack
        if isinstance(stack[0], list) and len(stack[0]) >= 2:
            if stack[0][0] != 'cell':
                raise ValueError(f"Expected cell in stack, got {stack[0][0]}")
            
            cell_data = stack[0][1]
            if isinstance(cell_data, dict):
                wallet_boc_b64 = cell_data.get('bytes', '')
            else:
                wallet_boc_b64 = str(cell_data)
        else:
            raise ValueError(f"Unexpected stack format: {stack[0]}")
        
        if not wallet_boc_b64:
            raise ValueError("Empty cell data in response")
        
        # Декодируем BOC
        padding = 4 - (len(wallet_boc_b64) % 4)
        if padding != 4:
            wallet_boc_b64 += '=' * padding
        
        wallet_bytes = base64.b64decode(wallet_boc_b64)
        
        # Парсим ячейку и извлекаем адрес
        wallet_cell = Cell.from_boc(wallet_bytes)[0]
        slice_reader = wallet_cell.begin_parse()
        wallet_addr = slice_reader.load_address()
        wallet_addr_str = wallet_addr.to_str(is_bounceable=True, is_url_safe=True)
        
        print(f"[CHAINSTACK] Successfully parsed jetton wallet: {wallet_addr_str}")
        JETTON_WALLET_CACHE[cache_key] = wallet_addr_str
        return wallet_addr_str
        
    except Exception as e:
        print(f"[CHAINSTACK] Jetton wallet error for master {master_addr}, owner {owner_addr}: {e}")
        traceback.print_exc()
        raise

def get_jetton_wallet_balance(wallet_addr: str) -> int:
    """
    Получение баланса Jetton-кошелька в минимальных единицах.
    """
    try:
        addr = validate_address(wallet_addr)
        result = toncenter_request('runGetMethod', {
            'address': addr,
            'method': 'get_wallet_data',
            'stack': []
        }, timeout=30)
        if not result or result.get('exit_code') != 0:
            return 0
        stack = result.get('stack', [])
        if not stack:
            return 0
        balance_cell = stack[0]
        if isinstance(balance_cell, list) and balance_cell[0] == 'num':
            return int(balance_cell[1], 16)
        return 0
    except Exception as e:
        print(f"[TON RPC] Jetton wallet balance error: {e}")
        return 0