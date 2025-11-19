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

load_dotenv()

# Конфигурация
TESTNET = os.environ.get("TESTNET", "False") == "True"
BASE_URL = os.environ.get("BASE_URL", "https://toncenter.com/api/v2")
API_KEY = os.environ.get("API_KEY")


def toncenter_request(method, params=None, retries=3, timeout=30):
    """
    Синхронный запрос к TON Center API с retry логикой
    
    Args:
        method: Метод JSON-RPC (например, 'getAddressInformation', 'runGetMethod')
        params: Параметры запроса
        retries: Количество попыток при ошибке
        timeout: Таймаут запроса в секундах
    
    Returns:
        dict: Результат запроса или None при ошибке
    """
    url = f"{BASE_URL}/jsonRPC"
    headers = {
        'Content-Type': 'application/json',
        'X-API-Key': API_KEY
    }
    payload = {
        'id': 1,
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
                continue
            return data.get('result', {})
        except Exception as e:
            print(f"[TON RPC] Attempt {attempt+1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    
    print(f"[TON RPC] All retries failed for {method}")
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
            addr = Address(addr_str, is_bounceable=True)
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
        tuple: (reserve_from, reserve_to) - резервы токенов в нано-единицах
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
            return 1000000, 2000000

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

        reserves = sorted(reserves, reverse=True)[:2][::-1]

        if len(reserves) >= 2:
            return reserves[-1], reserves[0]
            
        return 1000000, 2000000

    except Exception as e:
        print(f"[TON RPC] Reserves error: {e}")
        return 1000000, 2000000


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
            return 0

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


def get_jetton_wallet(master_addr: str, owner_addr: str):
    """
    Получение адреса Jetton-кошелька пользователя
    
    Args:
        master_addr: Адрес мастер-контракта Jetton
        owner_addr: Адрес владельца
    
    Returns:
        str: Адрес Jetton-кошелька
    
    Raises:
        ValueError: Если не удалось получить адрес кошелька
    """
    try:
        owner_builder = Builder()
        owner_builder.store_address(Address(owner_addr))
        owner_cell = owner_builder.end_cell()
        owner_boc = base64.b64encode(owner_cell.to_boc()).decode('utf-8')
        
        result = toncenter_request('runGetMethod', {
            'address': master_addr,
            'method': 'get_wallet_address',
            'stack': [['tvm.cell', owner_boc]]
        }, timeout=30)
        
        if not result or result.get('exit_code') != 0:
            raise ValueError("Failed to get Jetton wallet")
        
        stack = result['stack']
        if len(stack) < 1 or stack[0][0] != 'tvm.cell':
            raise ValueError("Invalid wallet address in stack")
        
        wallet_boc_b64 = stack[0][1]
        wallet_bytes = base64.b64decode(wallet_boc_b64)
        wallet_cell = Cell.from_boc(wallet_bytes)[0]
        slice = wallet_cell.begin_parse()
        wallet_addr = slice.load_address().to_str(is_bounceable=True, is_url_safe=True)
        return wallet_addr
    except Exception as e:
        print(f"[TON RPC] Jetton wallet error: {e}")
        raise

