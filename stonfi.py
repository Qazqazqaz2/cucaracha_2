"""
Рабочий модуль для операций со StonFi DEX (v2)
Генерирует корректные payload для свапов TON и Jetton через StonFi Router
"""

import os
import time
import base64
import random
from pytoniq_core import Address
from pytoniq_core.boc import Builder
from dotenv import load_dotenv

load_dotenv()

# Константы STON.fi
STONFI_ROUTER = os.environ.get(
    "STONFI_ROUTER",
    "EQCgn7fFRJNRJzYF003BgXYbG7xQS-3aTS4SiiL_F5mpxYjZ"   # Router v2 (mainnet)
)

STONFI_PROXY_TON = os.environ.get(
    "STONFI_PROXY_TON",
    "EQD5WQ2lLgyRcA3Nj0CsgYUL9FatX6y6I81dW4ZC7NmzxvIB"   # TON Proxy Jetton Wallet
)

STONFI_GAS_AMOUNT = int(float(os.environ.get("STONFI_GAS_AMOUNT", "0.25")) * 1_000_000_000)


def to_nano(amount: float) -> int:
    return int(amount * 1_000_000_000)


def generate_query_id():
    timestamp = int(time.time() * 1000)
    random_part = random.randint(0, 65535)
    return (timestamp << 16) | random_part


# ============================================================
#                 MAIN SWAP PAYLOAD BUILDER
# ============================================================

def create_swap_payload(pool_address: str, user_address: str, amount: int, min_out: int, from_token: str = "TON"):
    """
    Создание payload для свопа через StonFi v2
    """

    pool = Address(pool_address)
    user = Address(user_address)
    query_id = generate_query_id()

    # ------------------------------
    #   1) Строим swap params
    # ------------------------------

    params = Builder()
    params.store_uint(int(time.time()) + 300, 32)      # valid_until (5 минут)
    params.store_address(user)                         # destination
    params.store_address(None)                         # referral_address
    params.store_maybe_ref(None)                       # fulfill_payload
    params.store_maybe_ref(None)                       # reject_payload
    params_cell = params.end_cell()

    # ------------------------------
    #   TON → Jetton / Jetton → TON
    # ------------------------------

    if from_token == "TON":

        # Stonfi требует отправлять TON → через Proxy TON Jetton Wallet
        # Это payload для swap (op = 0x6664de2a)
        swap_step = Builder()
        swap_step.store_address(pool)
        swap_step.store_uint(0, 1)             # swap_type
        swap_step.store_coins(min_out)
        swap_step.store_maybe_ref(None)
        swap_step_cell = swap_step.end_cell()

        fwd = Builder()
        fwd.store_uint(0xe3a0d482, 32)         # forward op
        fwd.store_ref(swap_step_cell)
        fwd.store_ref(params_cell)
        fwd_cell = fwd.end_cell()

        # отправляется как transfer_notification к Router
        cell = Builder()
        cell.store_uint(0xf8a7ea5, 32)         # transfer_notification
        cell.store_uint(query_id, 64)
        cell.store_coins(amount)
        cell.store_address(Address(STONFI_ROUTER))
        cell.store_address(user)
        cell.store_maybe_ref(None)
        cell.store_coins(to_nano(0.15))        # gas forward
        cell.store_ref(fwd_cell)
        cell = cell.end_cell()

    else:
        # ------------------------------
        #          Jetton → Jetton
        # ------------------------------

        step = Builder()
        step.store_address(pool)
        step.store_uint(0, 1)
        step.store_coins(min_out)
        step.store_maybe_ref(None)
        step_cell = step.end_cell()

        fwd = Builder()
        fwd.store_uint(0xe3a0d482, 32)
        fwd.store_ref(step_cell)
        fwd.store_ref(params_cell)
        fwd_cell = fwd.end_cell()

        # transfer_notification jetton → Router
        cell = Builder()
        cell.store_uint(0xf8a7ea5, 32)
        cell.store_uint(query_id, 64)
        cell.store_coins(amount)
        cell.store_address(Address(STONFI_ROUTER))
        cell.store_address(user)
        cell.store_maybe_ref(None)
        cell.store_coins(to_nano(0.15))
        cell.store_ref(fwd_cell)
        cell = cell.end_cell()

    boc = base64.b64encode(cell.to_boc()).decode()
    print(f"[StonFi] Generated swap payload: {boc[:80]}...")
    return boc


# ============================================================
#                SIMPLE DEPOSIT PAYLOAD
# ============================================================

def create_deposit_payload(order_id=""):
    builder = Builder()
    builder.store_uint(0, 32)
    builder.store_uint(0, 64)
    return base64.b64encode(builder.end_cell().to_boc()).decode()


# ============================================================
#                   GET POOL INFO
# ============================================================

def get_pool_info(pool_address: str):
    from ton_rpc import get_pool_reserves
    try:
        r0, r1 = get_pool_reserves(pool_address)
        return {
            "address": pool_address,
            "reserve_from": r0,
            "reserve_to": r1,
            "dex": "StonFi"
        }
    except Exception as e:
        print(f"[StonFi] Error: {e}")
        return None
