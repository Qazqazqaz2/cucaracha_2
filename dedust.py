"""
Модуль для операций с DeDust DEX
Содержит функции для создания payload для свопов и депозитов через DeDust
"""
import os
import time
import base64
import random
from pytoniq_core import Address
from pytoniq_core.boc import Builder
from dotenv import load_dotenv

load_dotenv()

# Константы DeDust
DEDUST_NATIVE_VAULT = os.environ.get("DEDUST_NATIVE_VAULT")
DEDUST_FACTORY = os.environ.get("DEDUST_FACTORY")
DEDUST_GAS_AMOUNT = int(float(os.environ.get("DEDUST_GAS_AMOUNT", "0.3")) * 1_000_000_000)


def to_nano(amount: float, currency: str = "ton") -> int:
    """Конвертация суммы в нано-единицы"""
    if currency != "ton":
        raise ValueError("Only TON supported")
    return int(amount * 1_000_000_000)


def generate_query_id():
    """Генерация уникального query_id для транзакции"""
    timestamp = int(time.time() * 1000)
    random_part = random.randint(0, 65535)
    return (timestamp << 16) | random_part


def create_swap_payload(pool_address: str, user_address: str, amount: int, min_out: int, from_token: str = "TON"):
    """
    Создание payload для свопа через DeDust
    
    Args:
        pool_address: Адрес пула DeDust
        user_address: Адрес пользователя
        amount: Количество входных токенов в нано-единицах
        min_out: Минимальное количество выходных токенов в нано-единицах
        from_token: Тип входного токена ("TON" или адрес Jetton)
    
    Returns:
        str: Base64-encoded BOC payload
    """
    pool_addr = Address(pool_address)
    user_addr = Address(user_address)
    query_id = generate_query_id()

    if from_token == "TON":
        # Своп TON -> Jetton через Native Vault
        params = Builder()
        params.store_uint(int(time.time()) + 300, 32)  # valid_until
        params.store_address(user_addr)  # destination
        params.store_address(None)  # referral_address
        params.store_maybe_ref(None)  # fulfill_payload
        params.store_maybe_ref(None)  # reject_payload
        params_cell = params.end_cell()

        cell = Builder()
        cell.store_uint(0xea06185d, 32)  # op code для swap через Native Vault
        cell.store_uint(query_id, 64)
        cell.store_coins(amount)
        cell.store_address(pool_addr)
        cell.store_uint(0, 1)  # swap_type
        cell.store_coins(min_out)
        cell.store_maybe_ref(None)
        cell.store_ref(params_cell)
        cell = cell.end_cell()
    else:
        # Своп Jetton -> TON или Jetton -> Jetton
        params = Builder()
        params.store_uint(int(time.time()) + 300, 32)  # valid_until
        params.store_address(user_addr)  # destination
        params.store_address(None)  # referral_address
        params.store_maybe_ref(None)  # fulfill_payload
        params.store_maybe_ref(None)  # reject_payload
        params_cell = params.end_cell()

        step = Builder()
        step.store_address(pool_addr)
        step.store_uint(0, 1)  # swap_type
        step.store_coins(min_out)
        step.store_maybe_ref(None)
        step_cell = step.end_cell()

        fwd = Builder()
        fwd.store_uint(0xe3a0d482, 32)  # op code для forward
        fwd.store_ref(step_cell)
        fwd.store_ref(params_cell)
        fwd_cell = fwd.end_cell()

        # DeDust Router адрес (может быть настроен через env)
        router_address = os.environ.get("DEDUST_ROUTER", "EQAYqo4u7VF0fa4DPAebk4g9lBytj2VFny7pzXR0trjtXQaO")
        
        cell = Builder()
        cell.store_uint(0xf8a7ea5, 32)  # op code для transfer_notification
        cell.store_uint(query_id, 64)
        cell.store_coins(amount)
        cell.store_address(Address(router_address))
        cell.store_address(user_addr)
        cell.store_maybe_ref(None)
        cell.store_coins(to_nano(0.15))  # forward_ton_amount
        cell.store_ref(fwd_cell)
        cell = cell.end_cell()

    boc = base64.b64encode(cell.to_boc()).decode('utf-8')
    print(f"[DeDust] Generated swap payload BOC: {boc[:100]}...")
    return boc


def create_deposit_payload(order_id: str = ""):
    """
    Создание payload для депозита на кошелек ордеров
    
    Args:
        order_id: ID ордера (опционально, для логирования)
    
    Returns:
        str: Base64-encoded BOC payload
    """
    # Простой transfer без дополнительных данных
    # В реальном приложении здесь можно добавить комментарий с order_id
    builder = Builder()
    builder.store_uint(0, 32)  # op=0 для простого перевода
    builder.store_uint(0, 64)  # query_id
    return base64.b64encode(builder.end_cell().to_boc()).decode('utf-8')


def get_pool_info(pool_address: str):
    """
    Получение информации о пуле DeDust
    
    Args:
        pool_address: Адрес пула
    
    Returns:
        dict: Информация о пуле (резервы, комиссии и т.д.)
    """
    from ton_rpc import get_pool_reserves
    
    try:
        reserve_from, reserve_to = get_pool_reserves(pool_address)
        return {
            'address': pool_address,
            'reserve_from': reserve_from,
            'reserve_to': reserve_to,
            'dex': 'DeDust'
        }
    except Exception as e:
        print(f"[DeDust] Error getting pool info: {e}")
        return None

