from flask import Flask, render_template, request, jsonify
import json
import os
import time
import random
import base64
import requests
from pytoniq_core import Address, Cell
from pytoniq_core.boc import Builder
import asyncio
import threading
from datetime import datetime, timedelta
import traceback
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
POOLS_FILE = os.environ.get("POOLS_FILE", "pools.json")
ORDERS_FILE = os.environ.get("ORDERS_FILE", "orders.json")

# Конфиг
TESTNET = os.environ.get("TESTNET", "False") == "True"
BASE_URL = os.environ.get("BASE_URL", "https://toncenter.com/api/v2")
API_KEY = os.environ.get("API_KEY")
ORDER_WALLET_MNEMONIC = os.environ.get("ORDER_WALLET_MNEMONIC")

# ВАЖНО: Адреса и газ
DEDUST_NATIVE_VAULT = os.environ.get("DEDUST_NATIVE_VAULT")
DEDUST_FACTORY = os.environ.get("DEDUST_FACTORY")
STONFI_PROXY_TON = os.environ.get("STONFI_PROXY_TON")

# Заменяем to_nano на ручную конверсию
def to_nano(amount: float, currency: str = "ton") -> int:
    if currency != "ton":
        raise ValueError("Only TON supported")
    return int(amount * 1_000_000_000)

DEDUST_GAS_AMOUNT = to_nano(0.3)
STONFI_GAS_AMOUNT = to_nano(0.25)

# TON как токен (addr_none)
TON_AS_TOKEN = os.environ.get("TON_AS_TOKEN")

# SERVICE FEE: 0.25% для DeDust (стандарт для TON-USDT)
SERVICE_FEE_RATE = float(os.environ.get("SERVICE_FEE_RATE", 0.0025))

# Настройки по умолчанию
DEFAULT_SLIPPAGE = 1.0  # 1% по умолчанию

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

def load_orders():
    if os.path.exists(ORDERS_FILE):
        with open(ORDERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"orders": []}

def save_orders(orders_data):
    with open(ORDERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(orders_data, f, indent=2)

pools = load_pools()

def toncenter_request(method, params=None, retries=3, timeout=30):
    """Синхронный запрос с retry"""
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
                print(f"[API] Error in response: {data['error']}")
                continue
            return data.get('result', {})
        except Exception as e:
            print(f"[API] Attempt {attempt+1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    print(f"[API] All retries failed for {method}")
    return None

def validate_address(addr_str: str) -> str:
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
    try:
        addr = validate_address(address)
        result = toncenter_request('getAddressInformation', {'address': addr})
        if result:
            bal_nano = int(result.get('balance', 0))
            return bal_nano / (10 ** decimals)
        return 0
    except Exception as e:
        print(f"Balance error: {e}")
        return 0

def get_current_price(pool_addr: str):
    """Получает текущую цену из пула"""
    try:
        reserve_from, reserve_to = get_pool_reserves(pool_addr)
        if reserve_from > 0 and reserve_to > 0:
            return reserve_to / reserve_from
        return 0
    except Exception as e:
        print(f"Price error: {e}")
        return 0

def get_pool_reserves(pool_addr: str):
    """Получает резервы пула DEX"""
    try:
        pool_valid = validate_address(pool_addr)
        result = toncenter_request('runGetMethod', {
            'address': pool_valid,
            'method': 'get_reserves',
            'stack': []
        })
        
        if not result or result.get('exit_code', 1) != 0:
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
        print(f"Reserves error: {e}")
        return 1000000, 2000000

def get_expected_output(pool_addr: str, amount_nano: int, from_token_addr: str):
    """Использует get_expected_outputs с исправленным стеком"""
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
            print(f"get_expected_outputs failed: {result}")
            return 0

        stack = result['stack']
        if len(stack) < 1 or stack[0][0] != 'num':
            print(f"[EXPECTED] Invalid stack: {stack}")
            return 0
        out = int(stack[0][1], 16)
        print(f"[EXPECTED] Output: {out}")
        return out
    except Exception as e:
        print(f"Expected output error: {e}")
        return 0

def calculate_quote(from_amount: float, pool: dict):
    """Рассчитывает выходное количество токенов (fallback) + fees"""
    try:
        reserve_from, reserve_to = get_pool_reserves(pool['address'])
        print("RESERVES:", reserve_from, reserve_to)
        
        if reserve_from == 0 or reserve_to == 0:
            print(f"[QUOTE] Zero reserves: from={reserve_from}, to={reserve_to}")
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
        
        print(f"[QUOTE] {from_amount} {pool['from_token']} → {output:.6f} {pool['to_token']} | Fees: {total_fee*100:.2f}%")
        return output, f"{output:.6f} {pool.get('to_token', 'TOKEN')}"
    except Exception as e:
        print(f"Quote calculation error: {e}")
        return 0, f"Ошибка расчета: {e}"

def generate_query_id():
    timestamp = int(time.time() * 1000)
    random_part = random.randint(0, 65535)
    return (timestamp << 16) | random_part

def get_jetton_wallet(master_addr: str, owner_addr: str):
    """Получает адрес Jetton-кошелька пользователя"""
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
        print(f"Jetton wallet error: {e}")
        raise

def create_swap_payload(pool_address: str, user_address: str, amount: int, min_out: int, dex: str = "DeDust", from_token: str = ""):
    pool_addr = Address(pool_address)
    user_addr = Address(user_address)
    query_id = generate_query_id()

    if dex.upper() == "DEDUST" and from_token == "TON":
        params = Builder()
        params.store_uint(int(time.time()) + 300, 32)
        params.store_address(user_addr)
        params.store_address(None)
        params.store_maybe_ref(None)
        params.store_maybe_ref(None)
        params_cell = params.end_cell()

        cell = Builder()
        cell.store_uint(0xea06185d, 32)
        cell.store_uint(query_id, 64)
        cell.store_coins(amount)
        cell.store_address(pool_addr)
        cell.store_uint(0, 1)
        cell.store_coins(min_out)
        cell.store_maybe_ref(None)
        cell.store_ref(params_cell)
        cell = cell.end_cell()

    elif dex.upper() == "DEDUST":
        params = Builder()
        params.store_uint(int(time.time()) + 300, 32)
        params.store_address(user_addr)
        params.store_address(None)
        params.store_maybe_ref(None)
        params.store_maybe_ref(None)
        params_cell = params.end_cell()

        step = Builder()
        step.store_address(pool_addr)
        step.store_uint(0, 1)
        step.store_coins(min_out)
        step.store_maybe_ref(None)
        step_cell = step.end_cell()

        fwd = Builder()
        fwd.store_uint(0xe3a0d482, 32)
        fwd.store_ref(step_cell)
        fwd.store_ref(params_cell)
        fwd_cell = fwd.end_cell()

        cell = Builder()
        cell.store_uint(0xf8a7ea5, 32)
        cell.store_uint(query_id, 64)
        cell.store_coins(amount)
        cell.store_address(Address('EQAYqo4u7VF0fa4DPAebk4g9lBytj2VFny7pzXR0trjtXQaO'))
        cell.store_address(user_addr)
        cell.store_maybe_ref(None)
        cell.store_coins(to_nano(0.15))
        cell.store_ref(fwd_cell)
        cell = cell.end_cell()

    elif dex.upper() == "STONFI":
        cell = Builder()
        cell.store_uint(0x595f07bc, 32)
        cell.store_uint(query_id, 64)
        cell.store_coins(amount)
        cell.store_address(pool_addr)
        cell.store_address(user_addr)
        cell.store_coins(min_out)
        cell.store_uint(0, 1)
        cell = cell.end_cell()

    else:
        raise ValueError("Unsupported DEX")

    boc = base64.b64encode(cell.to_boc()).decode('utf-8')
    print(f"[DEBUG] Generated payload BOC: {boc[:100]}...")
    return boc

def create_deposit_payload(order_id: str):
    """Создает payload для депозита на кошелек ордеров"""
    # Простой transfer без дополнительных данных
    # В реальном приложении здесь можно добавить комментарий с order_id
    builder = Builder()
    builder.store_uint(0, 32)  # op=0 для простого перевода
    builder.store_uint(0, 64)  # query_id
    return base64.b64encode(builder.end_cell().to_boc()).decode('utf-8')

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
        updated = False
        for order in orders_data['orders']:
            if order.get('status') == 'unfunded' and order_is_funded(order):
                order['status'] = 'active'
                order['funded_at'] = datetime.now().isoformat()
                updated = True
                print(f"[ORDER] Ордер {order['id']} поступление средств подтверждено — активирован!")
        if updated:
            save_orders(orders_data)
    except Exception as e:
        print(f"[ORDER FUNDING] Error: {e}")
        traceback.print_exc()

def check_orders_execution():
    """Проверяет выполнение условий для ордеров"""
    try:
        orders_data = load_orders()
        active_orders = [o for o in orders_data['orders'] if o['status'] == 'active']
        
        if not active_orders:
            return
        
        # Получаем текущие цены для всех пар
        current_prices = {}
        for pool_name, pool in pools.items():
            current_prices[pool_name] = get_current_price(pool['address'])
        
        updated = False
        for order in active_orders:
            pair = order['pair']
            if pair not in current_prices or current_prices[pair] == 0:
                continue
                
            current_price = current_prices[pair]
            entry_price = order['entry_price']
            stop_loss = order.get('stop_loss')
            take_profit = order.get('take_profit')
            
            # Проверяем условия исполнения
            should_execute = False
            execution_type = ""
            
            if order['type'] == 'long':
                if stop_loss and current_price <= stop_loss:
                    should_execute = True
                    execution_type = "STOP_LOSS"
                elif take_profit and current_price >= take_profit:
                    should_execute = True
                    execution_type = "TAKE_PROFIT"
            elif order['type'] == 'short':
                if stop_loss and current_price >= stop_loss:
                    should_execute = True
                    execution_type = "STOP_LOSS"
                elif take_profit and current_price <= take_profit:
                    should_execute = True
                    execution_type = "TAKE_PROFIT"
            
            if should_execute:
                order['status'] = 'executed'
                order['executed_at'] = datetime.now().isoformat()
                order['execution_type'] = execution_type
                order['execution_price'] = current_price
                updated = True
                print(f"[ORDER] Executed {order['id']} at price {current_price} ({execution_type})")
        
        if updated:
            save_orders(orders_data)
            
    except Exception as e:
        print(f"[ORDER CHECK] Error: {e}")
        traceback.print_exc()

# Запускаем проверку ордеров в фоне
def start_order_checker():
    def checker_loop():
        while True:
            try:
                check_orders_funding()  # Проверить funding, после этого — исполнение
                check_orders_execution()
                time.sleep(30)
            except Exception as e:
                print(f"[ORDER CHECKER] Error: {e}")
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
        
        print(f"[SUCCESS] Swap ready: {amount} {from_token} → ~{output:.6f} {to_token} (slippage: {slippage}%)")
        
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
        print(f"[ERROR] Swap failed: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/orders', methods=['GET'])
def get_orders():
    """Получить список всех ордеров"""
    try:
        orders_data = load_orders()
        return jsonify(orders_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/orders', methods=['POST'])
def create_order():
    """Создать новый ордер"""
    data = request.json
    
    try:
        order_type = data.get('type')  # 'long' или 'short'
        pair = data.get('pair')  # 'TON-USDT'
        amount = float(data.get('amount', 0))
        entry_price = float(data.get('entry_price', 0))
        stop_loss = data.get('stop_loss')
        take_profit = data.get('take_profit')
        user_wallet = data.get('user_wallet')
        
        if order_type not in ['long', 'short']:
            return jsonify({'error': 'Тип ордера должен быть long или short'}), 400
        
        if pair not in pools:
            return jsonify({'error': f'Пара {pair} не поддерживается'}), 400
        
        if amount <= 0:
            return jsonify({'error': 'Сумма должна быть положительной'}), 400
        
        # Создаем ордер
        order_id = f"order_{int(time.time())}_{random.randint(1000, 9999)}"
        
        order = {
            'id': order_id,
            'type': order_type,
            'pair': pair,
            'amount': amount,
            'entry_price': entry_price,
            'stop_loss': float(stop_loss) if stop_loss else None,
            'take_profit': float(take_profit) if take_profit else None,
            'status': 'unfunded',  # статус "unfunded" (ожидает поступления depo)
            'created_at': datetime.now().isoformat(),
            'user_wallet': user_wallet,
            'order_wallet': order_wallet_address
        }
        
        # Сохраняем ордер
        orders_data = load_orders()
        orders_data['orders'].append(order)
        save_orders(orders_data)
        
        return jsonify({
            'success': True,
            'order': order,
            'message': 'Ордер создан, ожидает пополнения. Для активации переведите TON на адрес ордер-кошелька.'
        })
        
    except Exception as e:
        print(f"[ORDER CREATE] Error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/orders/<order_id>', methods=['DELETE'])
def cancel_order(order_id):
    """Отменить ордер"""
    try:
        orders_data = load_orders()
        
        for order in orders_data['orders']:
            if order['id'] == order_id and order['status'] == 'active':
                order['status'] = 'cancelled'
                order['cancelled_at'] = datetime.now().isoformat()
                save_orders(orders_data)
                return jsonify({'success': True, 'message': 'Ордер отменен'})
        
        return jsonify({'error': 'Ордер не найден или уже исполнен'}), 404
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/orders/<order_id>', methods=['PATCH'])
def update_order(order_id):
    """Редактировать активный или unfunded ордер: stop_loss, take_profit, amount"""
    data = request.json
    try:
        orders_data = load_orders()
        for order in orders_data['orders']:
            if order['id'] == order_id and order['status'] in ('active', 'unfunded'):
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
                    order['status'] = 'unfunded' # нужно будет заново пополнить если был active
                save_orders(orders_data)
                return jsonify({'success': True, 'order': order, 'message': 'Ордер успешно обновлён'})
        return jsonify({'error': 'Ордер не найден или недоступен для редактирования'}), 404
    except Exception as e:
        print(f"[ORDER UPDATE] Error: {e}")
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
        print(f"[DEPOSIT] Error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/pools')
def get_pools():
    return jsonify(pools)

if __name__ == '__main__':
    print("[STARTUP] Тестируем TON-USDT quote...")
    if 'TON-USDT' in pools:
        quote_out, _ = calculate_quote(1, pools['TON-USDT'])
        print(f"[STARTUP] 1 TON ≈ {quote_out:.6f} USDT")
    
    print(f"[STARTUP] Order wallet address: {order_wallet_address}")
    print(f"[STARTUP] Order wallet balance: {get_balance(order_wallet_address)} TON")
    
    app.run(debug=True, port=5000)
