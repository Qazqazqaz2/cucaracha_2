from flask import Flask, render_template, request, jsonify
import json
import os
import time
import random
import threading
from datetime import datetime, timedelta
import traceback
from dotenv import load_dotenv

import psycopg2
from contextlib import contextmanager

# Импорты из новых модулей
from ton_rpc import (
    get_balance,
    validate_address,
    get_pool_reserves,
    get_expected_output,
    get_jetton_wallet
)
from dedust import (
    create_swap_payload as dedust_create_swap_payload,
    create_deposit_payload as dedust_create_deposit_payload,
    DEDUST_GAS_AMOUNT
)
from stonfi import (
    create_swap_payload as stonfi_create_swap_payload,
    create_deposit_payload as stonfi_create_deposit_payload,
    STONFI_GAS_AMOUNT
)
from order_executor import execute_order_swap

load_dotenv()

app = Flask(__name__)
POOLS_FILE = os.environ.get("POOLS_FILE", "pools.json")
ORDERS_FILE = os.environ.get("ORDERS_FILE", "orders.json")

# Конфиг
TESTNET = os.environ.get("TESTNET", "False") == "True"
ORDER_WALLET_MNEMONIC = os.environ.get("ORDER_WALLET_MNEMONIC")
# ВАЖНО: Адреса и газ (для совместимости)
DEDUST_NATIVE_VAULT = os.environ.get("DEDUST_NATIVE_VAULT")
DEDUST_FACTORY = os.environ.get("DEDUST_FACTORY")
STONFI_PROXY_TON = os.environ.get("STONFI_PROXY_TON")


PG_CONN = os.environ.get("PG_CONN", "dbname=lpm user=postgres password=762341 host=localhost port=5432")

@contextmanager
def get_db_connection():
    """Контекстный менеджер для подключения к БД"""
    conn = None
    try:
        conn = psycopg2.connect(PG_CONN)
        yield conn
    except Exception as e:
        print(f"[ОШИБКА БД] {e}")
        raise
    finally:
        if conn:
            conn.close()

def init_db():
    """Инициализация БД"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Таблица ордеров
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS orders (
                        id VARCHAR(64) PRIMARY KEY,
                        type VARCHAR(16) NOT NULL,
                        pair VARCHAR(32) NOT NULL,
                        amount NUMERIC(20,8) NOT NULL,
                        entry_price NUMERIC(20,8) NOT NULL,
                        stop_loss NUMERIC(20,8),
                        take_profit NUMERIC(20,8),
                        user_wallet VARCHAR(80) NOT NULL,
                        order_wallet VARCHAR(80),
                        status VARCHAR(16) NOT NULL,
                        created_at TIMESTAMP NOT NULL,
                        funded_at TIMESTAMP,
                        opened_at TIMESTAMP,
                        executed_at TIMESTAMP,
                        execution_price NUMERIC(20,8),
                        execution_type VARCHAR(16),
                        cancelled_at TIMESTAMP,
                        pnl NUMERIC(20,8) DEFAULT 0,
                        price_at_creation NUMERIC(20,8)
                    )
                """)
                # Добавляем новые колонки для расширенной системы ордеров
                new_columns = [
                    ("opened_at", "TIMESTAMP"),
                    ("price_at_creation", "NUMERIC(20,8)"),
                    ("order_type", "VARCHAR(32)"),  # LIMIT, MARKET, STOP_LOSS, etc.
                    ("side", "VARCHAR(16)"),  # LONG, SHORT
                    ("limit_price", "NUMERIC(20,8)"),
                    ("stop_price", "NUMERIC(20,8)"),
                    ("max_slippage", "NUMERIC(10,4) DEFAULT 0.5"),
                    ("trailing_type", "VARCHAR(16)"),  # FIXED, PERCENTAGE
                    ("trailing_distance", "NUMERIC(20,8)"),
                    ("trailing_current_stop", "NUMERIC(20,8)"),
                    ("oco_group_id", "VARCHAR(64)"),
                    ("oco_related_ids", "TEXT"),  # JSON array
                    ("filled_quantity", "NUMERIC(20,8) DEFAULT 0"),
                    ("execution_error", "TEXT")  # Ошибка при исполнении ордера
                ]
                
                for col_name, col_type in new_columns:
                    try:
                        cur.execute(f"ALTER TABLE orders ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
                    except Exception as e:
                        print(f"[ПРИЛОЖЕНИЕ] Возможно колонка {col_name} уже есть: {e}")
                
                conn.commit()
                print("[ПРИЛОЖЕНИЕ] База данных инициализирована с расширенной системой ордеров")
    except Exception as e:
        print(f"[ПРИЛОЖЕНИЕ] Ошибка инициализации базы данных: {e}")

# Замените функции работы с ордерами
def load_orders(user_wallet=None):
    """Загрузка ордеров из БД - унифицированная версия"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if user_wallet:
                    cur.execute("""
                        SELECT id, type, pair, amount, entry_price, stop_loss, take_profit, 
                               user_wallet, order_wallet, status, created_at, funded_at, 
                               opened_at, executed_at, execution_price, execution_type, cancelled_at, pnl, price_at_creation,
                               max_slippage, execution_error
                        FROM orders 
                        WHERE user_wallet = %s 
                        ORDER BY created_at DESC
                    """, (user_wallet,))
                else:
                    cur.execute("""
                        SELECT id, type, pair, amount, entry_price, stop_loss, take_profit, 
                               user_wallet, order_wallet, status, created_at, funded_at, 
                               opened_at, executed_at, execution_price, execution_type, cancelled_at, pnl, price_at_creation,
                               max_slippage, execution_error
                        FROM orders 
                        ORDER BY created_at DESC
                    """)
                
                columns = [desc[0] for desc in cur.description]
                orders = []
                for row in cur.fetchall():
                    order = dict(zip(columns, row))
                    # Конвертируем Decimal в float для JSON и datetime в isoformat
                    for key, value in order.items():
                        if isinstance(value, datetime):  # Конвертация datetime
                            order[key] = value.isoformat()
                        elif hasattr(value, 'to_eng_string'):  # Decimal
                            order[key] = float(value)
                        elif value is None:
                            order[key] = None
                    orders.append(order)
                
                return {"orders": orders}
    except Exception as e:
        print(f"[ПРИЛОЖЕНИЕ] Ошибка загрузки ордеров: {e}")
        return {"orders": []}

def save_order(order):
    """Сохранение ордера в БД"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO orders (
                        id, type, pair, amount, entry_price, stop_loss, take_profit, 
                        user_wallet, order_wallet, status, created_at,
                        funded_at, opened_at, executed_at, execution_price, execution_type, cancelled_at, pnl, price_at_creation,
                        max_slippage, execution_error
                    ) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        stop_loss = EXCLUDED.stop_loss,
                        take_profit = EXCLUDED.take_profit,
                        amount = EXCLUDED.amount,
                        status = EXCLUDED.status,
                        funded_at = EXCLUDED.funded_at,
                        opened_at = EXCLUDED.opened_at,
                        executed_at = EXCLUDED.executed_at,
                        execution_price = EXCLUDED.execution_price,
                        execution_type = EXCLUDED.execution_type,
                        cancelled_at = EXCLUDED.cancelled_at,
                        pnl = EXCLUDED.pnl,
                        max_slippage = EXCLUDED.max_slippage,
                        execution_error = EXCLUDED.execution_error
                """, (
                    order['id'], order['type'], order['pair'], order['amount'], 
                    order['entry_price'], order.get('stop_loss'), order.get('take_profit'),
                    order['user_wallet'], order.get('order_wallet'), order['status'],
                    order['created_at'], order.get('funded_at'), order.get('opened_at'),
                    order.get('executed_at'), order.get('execution_price'), order.get('execution_type'),
                    order.get('cancelled_at'), order.get('pnl', 0), order.get('price_at_creation'),
                    order.get('max_slippage', DEFAULT_SLIPPAGE), order.get('execution_error')
                ))
                conn.commit()
                return True
    except Exception as e:
        print(f"[ПРИЛОЖЕНИЕ] Ошибка сохранения ордера: {e}")
        return False


# Вспомогательная функция для конверсии (используется в app.py)
def to_nano(amount: float, currency: str = "ton") -> int:
    if currency != "ton":
        raise ValueError("Only TON supported")
    return int(amount * 1_000_000_000)

# TON как токен (addr_none)
TON_AS_TOKEN = os.environ.get("TON_AS_TOKEN")

# SERVICE FEE: 0.25% для DeDust (стандарт для TON-USDT)
SERVICE_FEE_RATE = float(os.environ.get("SERVICE_FEE_RATE", 0.0025))

# Настройки по умолчанию
DEFAULT_SLIPPAGE = 10.0  # 1% по умолчанию

# Глобальные переменные для кошелька ордеров
# В реальном приложении здесь должен быть кошелек с мнемоникой
# Для демонстрации используем хардкодированный адрес
order_wallet_address = "UQD1V6ZNou__gvGZ9b-c69g9n1aXvSN4HJG1avp-AHDSRueL"

def load_pools():
    if os.path.exists(POOLS_FILE):
        with open(POOLS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f).get('pools', {})
    return {
        "TON-USDT": {
            "address": "EQCsgKK0mn7qY30BE8ACZAlfXJ7w5DJq0r9IX49sWg-z-opY",
            "dex": "DeDust",
            "from_token": "TON",
            "to_token": "USDT",
            "from_decimals": 9,
            "to_decimals": 6,
            "from_token_address": TON_AS_TOKEN,
            "to_token_address": "EQCxE6mUtQJKFnGfaROt1lZbDiiX1kCixRv7Nw2Id_sDs"
        }
    }

pools = load_pools()


def get_current_price(pool_addr: str, pool: dict = None):
    """
    Получает текущую цену из пула с учетом decimals токенов
    
    Args:
        pool_addr: Адрес пула
        pool: Информация о пуле (опционально, для определения decimals)
    
    Returns:
        float: Цена в правильном масштабе (например, 1.8 для TON-USDT)
    """
    try:
        reserve_from, reserve_to = get_pool_reserves(pool_addr)
        if reserve_from > 0 and reserve_to > 0:
            # Если передан pool, используем decimals для правильного расчета
            if pool:
                from_decimals = pool.get('from_decimals', 9)
                to_decimals = pool.get('to_decimals', 6)
                # Конвертируем резервы из нано-единиц в обычные единицы
                reserve_from_normalized = reserve_from / (10 ** from_decimals)
                reserve_to_normalized = reserve_to / (10 ** to_decimals)
                # Рассчитываем цену: сколько to_token за 1 from_token
                price = reserve_to_normalized / reserve_from_normalized
                return price
            else:
                # Fallback: для TON-USDT используем стандартные decimals
                # TON = 9 decimals, USDT = 6 decimals
                # Умножаем на 1000 чтобы компенсировать разницу в decimals
                return (reserve_to / reserve_from) * 1000
        return 0
    except Exception as e:
        print(f"[ПРИЛОЖЕНИЕ] Ошибка получения цены: {e}")
        return 0

def calculate_quote(from_amount: float, pool: dict):
    """Рассчитывает выходное количество токенов (fallback) + fees"""
    try:
        reserve_from, reserve_to = get_pool_reserves(pool['address'])
        print("[БОТ] РЕЗЕРВЫ:", reserve_from, reserve_to)
        
        if reserve_from == 0 or reserve_to == 0:
            print(f"[КОТИРОВКА] Нулевые резервы в пуле: from={reserve_from}, to={reserve_to}")
            return 0, "Ошибка: нулевые резервы в пуле"
        
        pool_fee = 0.003
        service_fee = SERVICE_FEE_RATE
        total_fee = service_fee
        
        input_amount_raw = int(from_amount * 10**pool['from_decimals'])
        
        if input_amount_raw <= 0:
            return 0, "Неверная сумма обмена"
        
        amount_in_with_fee = input_amount_raw * (1 - total_fee)
        numerator = amount_in_with_fee * reserve_to
        denominator = reserve_from + amount_in_with_fee
        
        if denominator == 0:
            return 0, "Ошибка расчета: деление на ноль"
            
        output_amount_raw = numerator // denominator
        output = output_amount_raw / 10**pool['to_decimals']
        
        print(f"[КОТИРОВКА] {from_amount} {pool['from_token']} → {output:.6f} {pool['to_token']} | Комиссия: {total_fee*100:.2f}%")
        return output, f"{output:.6f} {pool.get('to_token', 'TOKEN')}"
    except Exception as e:
        print(f"[КОТИРОВКА] Ошибка расчета: {e}")
        return 0, f"Ошибка расчета: {e}"

def create_swap_payload(pool_address: str, user_address: str, amount: int, min_out: int, dex: str = "DeDust", from_token: str = ""):
    """
    Создает payload для свопа через соответствующий DEX
    
    Args:
        pool_address: Адрес пула
        user_address: Адрес пользователя
        amount: Количество входных токенов в нано-единицах
        min_out: Минимальное количество выходных токенов в нано-единицах
        dex: Название DEX ("DeDust" или "StonFi")
        from_token: Тип входного токена ("TON" или адрес Jetton)
    
    Returns:
        str: Base64-encoded BOC payload
    """
    if dex.upper() == "DEDUST":
        return dedust_create_swap_payload(pool_address, user_address, amount, min_out, from_token)
    elif dex.upper() == "STONFI":
        return stonfi_create_swap_payload(pool_address, user_address, amount, min_out, from_token)
    else:
        raise ValueError(f"Unsupported DEX: {dex}")

def create_deposit_payload(order_id: str = ""):
    """
    Создает payload для депозита на кошелек ордеров
    Использует DeDust формат по умолчанию (можно расширить для выбора DEX)
    """
    return dedust_create_deposit_payload(order_id)

def order_is_funded(order):
    '''Проверить, достаточно ли средств на ордер-кошельке для ордера'''
    if order.get('status') != 'unfunded':
        return False
    
    # Проверяем баланс кошелька ордеров
    balance = get_balance(order_wallet_address)
    required_amount = order['amount'] + 0.1  # +0.1 TON для газа
    
    return balance >= required_amount

def check_orders_funding():
    '''Проверка "поступили ли нужные средства для ордеров"'''
    try:
        orders_data = load_orders()
        for order in orders_data['orders']:
            if order.get('status') == 'unfunded' and order_is_funded(order):
                order['status'] = 'waiting_entry'  # Меняем на waiting_entry вместо active
                order['funded_at'] = datetime.now().isoformat()
                save_order(order)
                print(f"[ОРДЕР] Ордер {order['id']} - поступление средств подтверждено, ожидает достижения цены входа!")
    except Exception as e:
        print(f"[ПОПОЛНЕНИЕ ОРДЕРА] Ошибка: {e}")
        traceback.print_exc()

def check_orders_execution():
    """Проверяет выполнение условий для ордеров"""
    try:
        orders_data = load_orders()
        # Проверяем ордера в статусах waiting_entry и opened
        waiting_orders = [o for o in orders_data['orders'] if o['status'] == 'waiting_entry']
        opened_orders = [o for o in orders_data['orders'] if o['status'] == 'opened']
        
        # Получаем текущие цены для всех пар
        current_prices = {}
        for pool_name, pool in pools.items():
            current_prices[pool_name] = get_current_price(pool['address'], pool)
        
        # Проверяем ордера, ожидающие достижения entry_price
        for order in waiting_orders:
            pair = order['pair']
            if pair not in current_prices or current_prices[pair] == 0:
                continue
            
            current_price = float(current_prices[pair])
            entry_price = float(order['entry_price'])
            price_at_creation_raw = order.get('price_at_creation')
            
            # Если price_at_creation не сохранена, используем текущую цену как отправную точку
            if price_at_creation_raw is None:
                price_at_creation = current_price
                print(f"[ПРОВЕРКА ОРДЕРА] Внимание: price_at_creation не найден для ордера {order['id']}, используется текущая цена: {current_price:.6f}")
            else:
                price_at_creation = float(price_at_creation_raw)
            
            # Определяем, достигнута ли entry_price в нужном направлении
            entry_reached = False
            
            # Получаем slippage из ордера или используем значение по умолчанию
            order_slippage = float(order.get('max_slippage', DEFAULT_SLIPPAGE))
            
            # Используем slippage для определения допустимого диапазона цен вокруг entry_price
            # Slippage определяет, насколько цена может отклониться от entry_price
            slippage_multiplier = order_slippage / 100.0  # Конвертируем проценты в множитель
            
            if order['type'] == 'long':
                # LONG ордер: покупаем когда цена достигает entry_price
                # Если цена была ниже entry_price, ждем роста до entry_price или выше (buy stop)
                # Если цена была выше entry_price, ждем падения до entry_price или ниже (buy limit)
                if price_at_creation < entry_price:
                    # Buy Stop: цена была ниже, ждем роста до entry_price или выше
                    # С учетом slippage: цена должна быть >= entry_price * (1 - slippage)
                    min_entry_price = entry_price * (1 - slippage_multiplier)
                    entry_reached = current_price >= min_entry_price
                else:
                    # Buy Limit: цена была выше, ждем падения до entry_price или ниже
                    # С учетом slippage: цена должна быть <= entry_price * (1 + slippage)
                    max_entry_price = entry_price * (1 + slippage_multiplier)
                    entry_reached = current_price <= max_entry_price
            elif order['type'] == 'short':
                # SHORT ордер: продаем когда цена достигает entry_price
                # Если цена была выше entry_price, ждем падения до entry_price или ниже (sell stop)
                # Если цена была ниже entry_price, ждем роста до entry_price или выше (sell limit)
                if price_at_creation > entry_price:
                    # Sell Stop: цена была выше, ждем падения до entry_price или ниже
                    # С учетом slippage: цена должна быть <= entry_price * (1 + slippage)
                    max_entry_price = entry_price * (1 + slippage_multiplier)
                    entry_reached = current_price <= max_entry_price
                else:
                    # Sell Limit: цена была ниже, ждем роста до entry_price или выше
                    # С учетом slippage: цена должна быть >= entry_price * (1 - slippage)
                    min_entry_price = entry_price * (1 - slippage_multiplier)
                    entry_reached = current_price >= min_entry_price
            
            print(entry_reached)

            # Добавляем отладочный вывод для диагностики
            if order['type'] == 'long':
                if price_at_creation < entry_price:
                    min_entry = entry_price * (1 - slippage_multiplier)
                    print(f"[ПРОВЕРКА ОРДЕРА] Ордер {order['id']}: Длинный Buy Stop, текущая={current_price:.6f}, вход={entry_price:.6f}, мин. вход={min_entry:.6f}, цена_создания={price_at_creation:.6f}, slippage={order_slippage}%, entry_reached={entry_reached}")
                else:
                    max_entry = entry_price * (1 + slippage_multiplier)
                    print(f"[ПРОВЕРКА ОРДЕРА] Ордер {order['id']}: Длинный Buy Limit, текущая={current_price:.6f}, вход={entry_price:.6f}, макс. вход={max_entry:.6f}, цена_создания={price_at_creation:.6f}, slippage={order_slippage}%, entry_reached={entry_reached}")                    
            else:
                if price_at_creation > entry_price:
                    max_entry = entry_price * (1 + slippage_multiplier)
                    print(f"[ПРОВЕРКА ОРДЕРА] Ордер {order['id']}: Короткий Sell Stop, текущая={current_price:.6f}, вход={entry_price:.6f}, макс. вход={max_entry:.6f}, цена_создания={price_at_creation:.6f}, slippage={order_slippage}%, entry_reached={entry_reached}")
                else:
                    min_entry = entry_price * (1 - slippage_multiplier)
                    print(f"[ПРОВЕРКА ОРДЕРА] Ордер {order['id']}: Короткий Sell Limit, текущая={current_price:.6f}, вход={entry_price:.6f}, мин. вход={min_entry:.6f}, цена_создания={price_at_creation:.6f}, slippage={order_slippage}%, entry_reached={entry_reached}")
            
            if entry_reached:
                # Позиция открыта, меняем статус на opened
                order['status'] = 'opened'
                order['opened_at'] = datetime.now().isoformat()
                order['execution_price'] = entry_price  # Используем entry_price как цену открытия
                save_order(order)
                print(f"[ОРДЕР] Открыт {order['id']} по цене входа {entry_price} (текущая: {current_price:.6f}, была: {price_at_creation:.6f})")
        
        # Проверяем открытые ордера на stop_loss и take_profit
        for order in opened_orders:
            pair = order['pair']
            if pair not in current_prices or current_prices[pair] == 0:
                continue
                
            current_price = current_prices[pair]
            entry_price = order['entry_price']
            stop_loss = order.get('stop_loss')
            take_profit = order.get('take_profit')
            
            # Проверяем условия исполнения (SL/TP)
            should_execute = False
            execution_type = ""
            
            if order['type'] == 'long':
                if stop_loss and current_price <= stop_loss:
                    should_execute = True
                    execution_type = "STOP_LOSS"
                    order['pnl'] = (stop_loss - entry_price) * order['amount']
                elif take_profit and current_price >= take_profit:
                    should_execute = True
                    execution_type = "TAKE_PROFIT"
                    order['pnl'] = (take_profit - entry_price) * order['amount']
            elif order['type'] == 'short':
                if stop_loss and current_price >= stop_loss:
                    should_execute = True
                    execution_type = "STOP_LOSS"
                    order['pnl'] = (entry_price - stop_loss) * order['amount']
                elif take_profit and current_price <= take_profit:
                    should_execute = True
                    execution_type = "TAKE_PROFIT"
                    order['pnl'] = (entry_price - take_profit) * order['amount']
            
            if should_execute:
                # Выполняем реальный обмен через DEX
                pair = order['pair']
                if pair in pools:
                    pool = pools[pair]
                    swap_result = execute_order_swap(
                        order=order,
                        pool=pool,
                        order_wallet_address=order_wallet_address,
                        order_wallet_mnemonic=ORDER_WALLET_MNEMONIC,
                        slippage=DEFAULT_SLIPPAGE
                    )
                    
                    if swap_result.get('success'):
                        order['status'] = 'executed'
                        order['executed_at'] = datetime.now().isoformat()
                        order['execution_type'] = execution_type
                        order['swap_result'] = swap_result  # Сохраняем результат обмена
                        
                        if swap_result.get('transaction_sent'):
                            order['transaction_hash'] = swap_result.get('transaction', {}).get('hash')
                            print(f"[ОРДЕР] Исполнен и произведён обмен {order['id']} по цене {current_price} ({execution_type}), PnL: {order.get('pnl', 0)}")
                            print(f"[ОРДЕР] Транзакция отправлена: {swap_result.get('message', '')}")
                        else:
                            print(f"[ОРДЕР] Исполнен {order['id']} по цене {current_price} ({execution_type}), PnL: {order.get('pnl', 0)}")
                            print(f"[ОРДЕР] Обмен подготовлен, но НЕ отправлен: {swap_result.get('message', '')}")
                            print(f"[ОРДЕР] 💡 Причина: {swap_result.get('message', 'Unknown')}")
                            print(f"[ОРДЕР] Данные транзакции: {swap_result.get('transaction', {})}")
                            print(f"[ОРДЕР] 💡 Для автоматической отправки убедитесь, что:")
                            print(f"    1. Установлен pytoniq: pip install pytoniq")
                            print(f"    2. Установлена переменная ORDER_WALLET_MNEMONIC в .env")
                            print(f"    3. Мнемоника соответствует адресу кошелька ордеров")
                    else:
                        # Ошибка при выполнении обмена
                        error_msg = swap_result.get('error', 'Unknown error')
                        print(f"[ОРДЕР] Ошибка исполнения для {order['id']}: {error_msg}")
                        order['status'] = 'execution_failed'
                        order['execution_error'] = error_msg
                else:
                    # Пул не найден, просто отмечаем как executed
                    print(f"[ОРДЕР] Пул {pair} не найден, отмечаем ордер исполненным без обмена")
                    order['status'] = 'executed'
                    order['executed_at'] = datetime.now().isoformat()
                    order['execution_type'] = execution_type
                
                # execution_price уже установлен при открытии (entry_price)
                save_order(order)
            
    except Exception as e:
        print(f"[ПРОВЕРКА ОРДЕРА] Ошибка: {e}")
        traceback.print_exc()

# Запускаем проверку ордеров в фоне
def start_order_checker():
    def checker_loop():
        while True:
            try:
                check_orders_funding()  # Проверить funding, после этого — исполнение
                check_orders_execution()  # Проверяем достижение entry_price и SL/TP
                time.sleep(30)
            except Exception as e:
                print(f"[ПРОВЕРКА ОРДЕРА] Ошибка: {e}")
                time.sleep(60)
    
    checker_thread = threading.Thread(target=checker_loop)
    checker_thread.daemon = True
    checker_thread.start()

# Запускаем проверку ордеров при старте
start_order_checker()

@app.route('/')
def index():
    return render_template('index.html', pools=pools, order_wallet_address=order_wallet_address)

@app.route('/balance', methods=['POST'])
def balance():
    data = request.json
    wallet_address = data.get('wallet_address')
    token = data.get('token', 'TON')
    
    try:
        if token == 'TON':
            bal = get_balance(wallet_address)
            return jsonify({'balance': bal})
        else:
            return jsonify({'balance': 0})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/quote', methods=['POST'])
def quote():
    data = request.json
    from_token = data.get('from_token')
    to_token = data.get('to_token')
    amount = float(data.get('amount', 0))
    slippage = float(data.get('slippage', DEFAULT_SLIPPAGE))

    if amount <= 0:
        return jsonify({'error': 'Введите положительную сумму'}), 400

    pair = f"{from_token}-{to_token}"
    if pair not in pools:
        return jsonify({'error': f'Пул {pair} не найден'}), 400

    pool = pools[pair]
    try:
        from_token_addr = pool.get('from_token_address', TON_AS_TOKEN)
        expected_out_nano = get_expected_output(pool['address'], int(amount * 10**pool['from_decimals']), from_token_addr)
        
        if expected_out_nano > 0:
            output = expected_out_nano / 10**pool['to_decimals']
            formatted = f"{output:.6f} {pool['to_token']}"
        else:
            output, formatted = calculate_quote(amount, pool)
        
        if output == 0:
            return jsonify({'error': formatted}), 400
        
        service_fee = amount * SERVICE_FEE_RATE
        
        min_output = output * (1 - slippage / 100)
        
        return jsonify({
            'quote': output, 
            'formatted': formatted,
            'min_output': min_output,
            'min_output_formatted': f"{min_output:.6f} {pool['to_token']}",
            'pool_address': pool['address'],
            'slippage': slippage,
            'fees': {
                'service_fee': service_fee,
                'service_rate': '0.25%',
                'pool_fee': '0.3%',
                'slippage': f'{slippage}%',
                'network_gas': '0.1-0.3 TON'
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/swap', methods=['POST'])
def swap():
    data = request.json
    wallet_address_raw = data.get('wallet_address')
    from_token = data.get('from_token')
    to_token = data.get('to_token')
    amount = float(data.get('amount', 0))
    slippage = float(data.get('slippage', DEFAULT_SLIPPAGE))

    if amount <= 0:
        return jsonify({'error': 'Invalid amount'}), 400

    pair = f"{from_token}-{to_token}"
    if pair not in pools:
        return jsonify({'error': 'Пул не найден'}), 400

    pool = pools[pair]
    try:
        wallet_address = validate_address(wallet_address_raw)
        pool_addr = validate_address(pool['address'])

        amount_nano = int(amount * 10**pool['from_decimals'])
        
        output, _ = calculate_quote(amount, pool)
        if output == 0:
            raise ValueError("Недостаточная ликвидность")
        
        expected_out_nano = int(output * 10**pool['to_decimals'])
        min_out_nano = int(expected_out_nano * (1 - slippage / 100))
        
        service_fee = amount * SERVICE_FEE_RATE

        if from_token == "TON":
            if pool['dex'] == "DeDust":
                dest_addr = DEDUST_NATIVE_VAULT
                gas = DEDUST_GAS_AMOUNT
            elif pool['dex'] == "StonFi":
                dest_addr = STONFI_PROXY_TON
                gas = STONFI_GAS_AMOUNT
            else:
                raise ValueError("Unsupported DEX")
            total_amount = amount_nano + gas
        else:
            dest_addr = get_jetton_wallet(pool['from_token_address'], wallet_address)
            gas = to_nano(0.2)
            total_amount = gas

        dest_valid = validate_address(dest_addr)

        payload = create_swap_payload(
            pool['address'], wallet_address, amount_nano, min_out_nano, 
            dex=pool.get('dex', 'DeDust'),
            from_token=from_token
        )
        
        print(f"[УСПЕХ] Своп готов: {amount} {from_token} → ~{output:.6f} {to_token} (slippage: {slippage}%)")
        
        return jsonify({
            'validUntil': int(time.time()) + 300,
            'messages': [{
                'address': dest_valid,
                'amount': str(total_amount),
                'payload': payload
            }],
            'transaction_details': {
                'label': f'Обмен: {amount} {from_token} → {output:.6f} {to_token}',
                'breakdown': {
                    'input': f'{amount} {from_token}',
                    'output_expected': f'{output:.6f} {to_token}',
                    'min_output': f'{min_out_nano / 10**pool["to_decimals"]:.6f} {to_token}',
                    'slippage': f'{slippage}%',
                    'service_fee': f'{service_fee:.6f} {from_token} (0.25%)',
                    'pool_fee': f'{amount * 0.003:.6f} {from_token} (0.3%)',
                    'network_gas': f'{gas / 1e9:.3f} TON',
                }
            },
            'debug': {
                'expected_out': output,
                'min_out': min_out_nano / 10**pool['to_decimals'],
                'gas': gas / 1e9,
                'slippage': slippage
            }
        })

    except Exception as e:
        print(f"[ОШИБКА] Ошибка при подготовке свопа: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/orders', methods=['GET'])
def get_orders():
    """Получить список ордеров пользователя"""
    try:
        user_wallet = request.args.get('user_wallet')
        orders_data = load_orders(user_wallet)
        return jsonify(orders_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/orders', methods=['POST'])
def create_order():
    """Создать новый ордер в БД с проверкой баланса"""
    data = request.json
    
    try:
        # Получаем текущий баланс кошелька ордеров
        current_balance = get_balance(order_wallet_address)
        
        # Рассчитываем общую сумму уже активных и ожидающих ордеров
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COALESCE(SUM(amount + 0.1), 0) as total_reserved 
                    FROM orders 
                    WHERE status IN ('active', 'unfunded')
                """)
                total_reserved = cur.fetchone()[0] or 0
        
        # Требуемая сумма для нового ордера
        order_amount = float(data.get('amount', 0))
        required_for_new_order = order_amount + 0.1  # + комиссия
        
        # Доступный баланс
        available_balance = current_balance - total_reserved
        
        if required_for_new_order > available_balance:
            return jsonify({
                'error': f'Недостаточно средств на кошельке ордеров. Доступно: {available_balance:.2f} TON, требуется: {required_for_new_order:.2f} TON'
            }), 400
        
        # Создаем ордер
        order_id = f"order_{int(time.time())}_{random.randint(1000, 9999)}"
        

        # Нормализуем адрес кошелька пользователя
        user_wallet_raw = data.get('user_wallet')
        try:
            user_wallet = validate_address(user_wallet_raw)
        except:
            user_wallet = user_wallet_raw  # Если не удалось нормализовать, используем как есть
        
        pair = data.get('pair')
        order_type = data.get('type')
        entry_price = float(data.get('entry_price', 0))
        stop_loss = float(data.get('stop_loss')) if data.get('stop_loss') else None
        take_profit = float(data.get('take_profit')) if data.get('take_profit') else None
        
        if pair not in pools:
            return jsonify({'error': f'Пул {pair} не найден'}), 400
        
        pool_info = pools[pair]
        current_price = get_current_price(pool_info['address'], pool_info)
        if current_price == 0:
            return jsonify({'error': 'Не удалось получить текущую цену'}), 500
        
        # Получаем slippage из запроса или используем значение по умолчанию
        order_slippage = float(data.get('slippage', DEFAULT_SLIPPAGE))
        
        order = {
            'id': order_id,
            'type': order_type,
            'pair': pair,
            'amount': order_amount,
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'user_wallet': user_wallet,
            'order_wallet': order_wallet_address,
            'status': 'unfunded',  # Все новые ордера создаются как unfunded
            'created_at': datetime.now().isoformat(),
            'funded_at': None,
            'opened_at': None,
            'price_at_creation': current_price,  # Сохраняем цену при создании
            'max_slippage': order_slippage  # Сохраняем slippage для ордера
        }
        
        print(f"[ОТЛАДКА] Создание ордера {order_id} со статусом: {order['status']}, entry_price: {entry_price}, current_price: {current_price}")
        
        # Проверяем, достаточно ли средств для немедленной активации
        if current_balance >= total_reserved + required_for_new_order:
            order['status'] = 'waiting_entry'  # Ждем достижения entry_price
            order['funded_at'] = datetime.now().isoformat()
            message = f'Ордер создан и активирован! Ожидает достижения цены входа {entry_price} USDT (текущая: {current_price} USDT).'
        else:
            message = f'Ордер создан, ожидает пополнения. Переведите {required_for_new_order:.2f} TON на {order_wallet_address} для активации!'
        
        if order_type == 'long':
            if stop_loss and stop_loss >= entry_price:
                return jsonify({'error': 'Для LONG Stop Loss должен быть ниже цены входа'}), 400
            if take_profit and take_profit <= entry_price:
                return jsonify({'error': 'Для LONG Take Profit должен быть выше цены входа'}), 400
            # Removed: if stop_loss and current_price <= stop_loss: ...
            # Removed: if take_profit and current_price >= take_profit: ...
        elif order_type == 'short':
            if stop_loss and stop_loss <= entry_price:
                return jsonify({'error': 'Для SHORT Stop Loss должен быть выше цены входа'}), 400
            if take_profit and take_profit >= entry_price:
                return jsonify({'error': 'Для SHORT Take Profit должен быть ниже цены входа'}), 400
            # Removed: if stop_loss and current_price >= stop_loss: ...
            # Removed: if take_profit and current_price <= take_profit: ...
        else:
            return jsonify({'error': 'Неверный тип ордера'}), 400

        if save_order(order):
            print(f"[АПИ] Ордер {order_id} успешно сохранён")
            # Проверяем, что ордер действительно сохранен
            saved_orders = load_orders(order['user_wallet'])
            print(f"[АПИ] После сохранения у пользователя {len(saved_orders.get('orders', []))} ордеров")
            return jsonify({
                'success': True,
                'order': order,
                'message': message,
                'available_balance': available_balance,
                'required': required_for_new_order
            })
        else:
            print(f"[АПИ] Ошибка при сохранении ордера {order_id}")
            return jsonify({'error': 'Ошибка сохранения ордера'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/user-orders', methods=['GET'])
def get_user_orders():
    """Получить все ордера пользователя"""
    try:
        user_wallet_raw = request.args.get('user_wallet')
        if not user_wallet_raw:
            return jsonify({'error': 'user_wallet parameter is required'}), 400
        
        # Нормализуем адрес для поиска
        try:
            user_wallet = validate_address(user_wallet_raw)
        except:
            user_wallet = user_wallet_raw  # Если не удалось нормализовать, используем как есть
        
        print(f"[АПИ] Загрузка ордеров для кошелька: {user_wallet} (исходный: {user_wallet_raw})")
        orders_data = load_orders(user_wallet)
        print(f"[АПИ] Найдено {len(orders_data.get('orders', []))} ордеров")
        
        # Если не нашли ордера с нормализованным адресом, попробуем с оригинальным
        if len(orders_data.get('orders', [])) == 0 and user_wallet != user_wallet_raw:
            print(f"[АПИ] Пробуем с исходным адресом: {user_wallet_raw}")
            orders_data_alt = load_orders(user_wallet_raw)
            if len(orders_data_alt.get('orders', [])) > 0:
                orders_data = orders_data_alt
                print(f"[АПИ] Найдено {len(orders_data.get('orders', []))} ордеров с исходным адресом")
        
        return jsonify(orders_data)
    except Exception as e:
        print(f"[АПИ] Ошибка при загрузке ордеров пользователя: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/orders/<order_id>', methods=['DELETE'])
def cancel_order(order_id):
    """Отменить ордер"""
    try:
        orders_data = load_orders()
        
        for order in orders_data['orders']:
            if order['id'] == order_id and order['status'] in ('unfunded', 'waiting_entry', 'opened', 'active'):
                order['status'] = 'cancelled'
                order['cancelled_at'] = datetime.now().isoformat()
                save_order(order)
                return jsonify({'success': True, 'message': 'Ордер отменен'})
        
        return jsonify({'error': 'Ордер не найден или уже исполнен/отменен'}), 404
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/orders/<order_id>', methods=['PATCH'])
def update_order(order_id):
    """Редактировать активный или unfunded ордер: stop_loss, take_profit, amount"""
    data = request.json
    try:
        orders_data = load_orders()
        for order in orders_data['orders']:
            if order['id'] == order_id and order['status'] in ('unfunded', 'waiting_entry', 'opened', 'active'):
                # Разрешаем менять SL/TP/amount только если не исполнен/не отменён
                if 'stop_loss' in data:
                    order['stop_loss'] = float(data['stop_loss']) if data['stop_loss'] is not None else None
                if 'take_profit' in data:
                    order['take_profit'] = float(data['take_profit']) if data['take_profit'] is not None else None
                if 'amount' in data:
                    # Если amount увеличивается — требует доп. funding! Можно усложнить логику при необходимости
                    new_amount = float(data['amount'])
                    if new_amount <= 0:
                        return jsonify({'error': 'Сумма должна быть положительной'}), 400
                    order['amount'] = new_amount
                    # Если ордер был opened, при изменении суммы нужно вернуть в waiting_entry
                    if order['status'] == 'opened':
                        order['status'] = 'waiting_entry'
                        order['opened_at'] = None
                    elif order['status'] in ('waiting_entry', 'active'):
                        order['status'] = 'unfunded'  # нужно будет заново пополнить
                save_order(order)
                return jsonify({'success': True, 'order': order, 'message': 'Ордер успешно обновлён'})
        return jsonify({'error': 'Ордер не найден или недоступен для редактирования'}), 404
    except Exception as e:
        print(f"[ОРДЕР ОБНОВЛЕНИЕ] Ошибка: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/order-wallet')
def get_order_wallet():
    """Получить адрес кошелька для ордеров"""
    try:
        balance = get_balance(order_wallet_address)
        return jsonify({
            'address': order_wallet_address,
            'balance': balance,
            'status': 'success'
        })
    except Exception as e:
        return jsonify({
            'address': order_wallet_address,
            'balance': 0,
            'status': 'error',
            'message': str(e)
        })

@app.route('/deposit-order', methods=['POST'])
def deposit_order():
    """Создать транзакцию для пополнения ордера"""
    data = request.json
    order_id = data.get('order_id')
    
    try:
        orders_data = load_orders()
        order = None
        for o in orders_data['orders']:
            if o['id'] == order_id and o['status'] == 'unfunded':
                order = o
                break
        
        if not order:
            return jsonify({'error': 'Ордер не найден или уже пополнен'}), 404
        
        # Создаем payload для перевода на кошелек ордеров
        amount_nano = to_nano(order['amount'] + 0.1)  # +0.1 TON для газа
        
        payload = create_deposit_payload(order_id)
        
        return jsonify({
            'validUntil': int(time.time()) + 300,
            'messages': [{
                'address': order_wallet_address,
                'amount': str(amount_nano),
                'payload': payload
            }],
            'transaction_details': {
                'label': f'Пополнение ордера {order_id}',
                'breakdown': {
                    'amount': f'{order["amount"]} TON',
                    'gas_fee': '0.1 TON',
                    'total': f'{order["amount"] + 0.1} TON'
                }
            }
        })
        
    except Exception as e:
        print(f"[ПОПОЛНЕНИЕ] Ошибка: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/pools')
def get_pools():
    return jsonify(pools)

@app.route('/current-price', methods=['GET'])
def get_current_price_api():
    """Получить текущую цену для real-time обновления"""
    try:
        pool_name = request.args.get('pool', 'TON-USDT')
        if pool_name not in pools:
            return jsonify({'error': 'Pool not found'}), 404
        
        pool = pools[pool_name]
        current_price = get_current_price(pool['address'], pool)
        
        return jsonify({
            'success': True,
            'pool': pool_name,
            'price': current_price,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        print(f"[АПИ] Ошибка получения текущей цены: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/price-history', methods=['GET'])
def get_price_history():
    """Получить историю цен для графика"""
    try:
        pool_name = request.args.get('pool', 'TON-USDT')
        minutes = request.args.get('minutes')
        hours = request.args.get('hours')
        
        # Определяем период запроса
        if minutes:
            period_minutes = float(minutes)
            interval_sql = f"INTERVAL '{int(period_minutes * 60)} seconds'"
        elif hours:
            period_hours = int(hours)
            interval_sql = f"INTERVAL '{period_hours} hours'"
        else:
            # По умолчанию 24 часа
            period_hours = 24
            interval_sql = "INTERVAL '24 hours'"
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Получаем данные за указанный период
                # Используем безопасный способ формирования запроса
                query = f"""
                    SELECT 
                        created_at,
                        price
                    FROM pool_snapshots
                    WHERE pool_name = %s 
                    AND created_at >= NOW() - {interval_sql}
                    ORDER BY created_at ASC
                """
                cur.execute(query, (pool_name,))
                
                rows = cur.fetchall()
                
                # Если данных мало и период больше часа, используем агрегированные данные
                if len(rows) < 10 and (hours or (minutes and float(minutes) >= 60)):
                    if hours:
                        query_agg = f"""
                            SELECT 
                                date_hour as created_at,
                                close_price as price
                            FROM pool_aggregated
                            WHERE pool_name = %s 
                            AND date_hour >= NOW() - {interval_sql}
                            ORDER BY date_hour ASC
                        """
                        cur.execute(query_agg, (pool_name,))
                        rows = cur.fetchall()
                
                # Форматируем данные для графика
                data = {
                    'labels': [],
                    'prices': []
                }
                
                for row in rows:
                    timestamp, price = row
                    # Конвертируем datetime в строку
                    if isinstance(timestamp, datetime):
                        data['labels'].append(timestamp.isoformat())
                    else:
                        data['labels'].append(str(timestamp))
                    
                    # Конвертируем Decimal в float
                    if hasattr(price, 'to_eng_string'):
                        data['prices'].append(float(price))
                    else:
                        data['prices'].append(float(price))
                
                return jsonify({
                    'success': True,
                    'pool': pool_name,
                    'data': data
                })
                
    except Exception as e:
        print(f"[АПИ] Ошибка получения истории цен: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# Новые API endpoints для расширенной системы ордеров
@app.route('/api/orders/create', methods=['POST'])
def create_advanced_order():
    """Создать ордер нового типа (LIMIT, MARKET, STOP_LOSS, TAKE_PROFIT, STOP_ENTRY)"""
    try:
        from order_engine import get_order_engine
        
        data = request.json
        engine = get_order_engine()
        
        # Валидация
        required_fields = ['symbol', 'quantity', 'order_type', 'side']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Создаем ордер
        order = engine.create_order({
            'symbol': data['symbol'],
            'quantity': data['quantity'],
            'order_type': data['order_type'],
            'side': data['side'],
            'limit_price': data.get('limit_price'),
            'stop_price': data.get('stop_price'),
            'take_profit': data.get('take_profit'),
            'stop_loss': data.get('stop_loss'),
            'max_slippage': data.get('max_slippage', 0.5),
            'user_wallet': data.get('user_wallet', ''),
            'order_wallet': order_wallet_address,
            'entry_price': data.get('entry_price'),
            'trailing_type': data.get('trailing_type'),
            'trailing_distance': data.get('trailing_distance'),
            'oco_group_id': data.get('oco_group_id'),
            'oco_related_ids': data.get('oco_related_ids', []),
        })
        
        return jsonify({
            'success': True,
            'order': order.to_dict(),
            'message': f'Order {order.id} created successfully'
        })
    except Exception as e:
        print(f"[АПИ] Ошибка создания ордера: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/orders/oco', methods=['POST'])
def create_oco_order():
    """Создать OCO ордер (связка TP и SL)"""
    try:
        from order_engine import get_order_engine
        
        data = request.json
        engine = get_order_engine()
        
        # Валидация
        if 'tp_order' not in data or 'sl_order' not in data:
            return jsonify({'error': 'Missing tp_order or sl_order'}), 400
        
        tp_data = data['tp_order']
        sl_data = data['sl_order']
        
        # Создаем OCO пару
        tp_order, sl_order = engine.create_oco_order(tp_data, sl_data)
        
        return jsonify({
            'success': True,
            'tp_order': tp_order.to_dict(),
            'sl_order': sl_order.to_dict(),
            'oco_group_id': tp_order.oco_group_id,
            'message': 'OCO order pair created successfully'
        })
    except Exception as e:
        print(f"[АПИ] Ошибка создания OCO ордера: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/orders/<order_id>/trailing', methods=['POST'])
def set_trailing_stop(order_id):
    """Установить трейлинг-стоп для существующего ордера"""
    try:
        from order_engine import get_order_engine
        from order_system import TrailingConfig, TrailingType
        
        data = request.json
        engine = get_order_engine()
        
        # Находим ордер
        if order_id not in engine.processor.orders:
            return jsonify({'error': 'Order not found'}), 404
        
        order = engine.processor.orders[order_id]
        
        # Создаем конфиг трейлинга
        trailing_type = TrailingType[data.get('trailing_type', 'FIXED').upper()]
        trailing_distance = float(data.get('trailing_distance', 0))
        
        order.trailing = TrailingConfig(
            type=trailing_type,
            distance=trailing_distance
        )
        
        # Сохраняем
        engine.save_order_to_db(order)
        
        return jsonify({
            'success': True,
            'order': order.to_dict(),
            'message': 'Trailing stop configured'
        })
    except Exception as e:
        print(f"[АПИ] Ошибка установки трейлинг-стопа: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/orders/slippage-stats', methods=['GET'])
def get_slippage_stats():
    """Получить статистику проскальзывания"""
    try:
        from order_engine import get_order_engine
        
        engine = get_order_engine()
        stats = engine.get_slippage_stats()
        
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        print(f"[АПИ] Ошибка получения статистики проскальзывания: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/orders/<order_id>', methods=['GET'])
def get_order_details(order_id):
    """Получить детали ордера"""
    try:
        from order_engine import get_order_engine
        
        engine = get_order_engine()
        
        if order_id not in engine.processor.orders:
            # Пытаемся загрузить из БД
            orders_data = load_orders()
            order_dict = next((o for o in orders_data.get('orders', []) if o['id'] == order_id), None)
            if order_dict:
                from order_engine import OrderEngine
                order = OrderEngine._convert_legacy_order(order_dict)
                if order:
                    return jsonify({
                        'success': True,
                        'order': order.to_dict()
                    })
            return jsonify({'error': 'Order not found'}), 404
        
        order = engine.processor.orders[order_id]
        return jsonify({
            'success': True,
            'order': order.to_dict()
        })
    except Exception as e:
        print(f"[АПИ] Ошибка получения деталей ордера: {e}")
        return jsonify({'error': str(e)}), 500

init_db()

if __name__ == '__main__':
    print("[ЗАПУСК] Тестируем TON-USDT котировку...")
    if 'TON-USDT' in pools:
        quote_out, _ = calculate_quote(1, pools['TON-USDT'])
        print(f"[ЗАПУСК] 1 TON ≈ {quote_out:.6f} USDT")
    
    print(f"[ЗАПУСК] Адрес кошелька для ордеров: {order_wallet_address}")
    print(f"[ЗАПУСК] Баланс кошелька для ордеров: {get_balance(order_wallet_address)} TON")
    
    app.run(debug=True, port=5000)
