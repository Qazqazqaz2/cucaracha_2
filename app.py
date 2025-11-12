from flask import Flask, render_template, request, jsonify
import json
import os
import time
import random
import base64
import requests
from pytoniq_core import Address, Cell
from pytoniq_core.boc import Builder

app = Flask(__name__)
POOLS_FILE = 'pools.json'

# Конфиг
TESTNET = False
BASE_URL = "https://toncenter.com/api/v2"
API_KEY = "256dd2ae98d77eded3d35bd4effd6c21afd92fb4d6c602ab9e9a9468872cd03a"

# ВАЖНО: Адреса и газ
DEDUST_NATIVE_VAULT = "EQDa4VOnTYlLvDJ0gZjNYm5PXfSmmtL6Vs6A_CZEtXCNICq_"   # Актуальный Native Vault (mainnet, ноябрь 2025)
DEDUST_FACTORY = "EQBfBWT7X2BHg9tXAxzhz2aKiNTU1tpt5NsiK0uSDW_YAJ67"
STONFI_PROXY_TON = "EQCM3B12QK1e4yZSf8GtBRT0aLMNyEsBc_DhVfRRtOEffLez"

# Заменяем to_nano на ручную конверсию
def to_nano(amount: float, currency: str = "ton") -> int:
    if currency != "ton":
        raise ValueError("Only TON supported")
    return int(amount * 1_000_000_000)

DEDUST_GAS_AMOUNT = to_nano(0.3)   # Увеличено для стабильности
STONFI_GAS_AMOUNT = to_nano(0.25)

# TON как токен (addr_none)
TON_AS_TOKEN = "EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c"

# SERVICE FEE: 0.25% для DeDust (стандарт для TON-USDT)
SERVICE_FEE_RATE = 0.0025  # 0.25%

def load_pools():
    if os.path.exists(POOLS_FILE):
        with open(POOLS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f).get('pools', {})
    # Fallback mock для TON-USDT (если файл пустой)
    return {
        "TON-USDT": {
            "address": "EQCsgKK0mn7qY30BE8ACZAlfXJ7w5DJq0r9IX49sWg-z-opY",  # Актуальный DeDust пул (volatile)
            "dex": "DeDust",
            "from_token": "TON",
            "to_token": "USDT",
            "from_decimals": 9,
            "to_decimals": 6,
            "from_token_address": TON_AS_TOKEN,
            "to_token_address": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs"
        }
    }

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

def get_pool_reserves(pool_addr: str):
    """Получает резервы пула DEX"""
    try:
        pool_valid = validate_address(pool_addr)
        result = toncenter_request('runGetMethod', {
            'address': pool_valid,
            'method': 'get_reserves',
            'stack': []
        })
        print("RES", result)
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
        print(reserves)

        if len(reserves) >= 2:
            return reserves[-1], reserves[0]

        return 1000000, 2000000

    except Exception as e:
        print(f"Reserves error: {e}")
        return 1000000, 2000000

def get_expected_output(pool_addr: str, amount_nano: int, from_token_addr: str):
    """Использует get_expected_outputs с исправленным стеком"""
    try:
        # Создаем ячейку с адресом токена
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
        
        # Комиссия пула DeDust + наша
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
        # SwapParams
        params = Builder()
        params.store_uint(int(time.time()) + 300, 32)  # deadline
        params.store_address(user_addr)               # recipient
        params.store_address(None)                    # referral
        params.store_maybe_ref(None)                  # fulfill
        params.store_maybe_ref(None)                  # reject
        params_cell = params.end_cell()

        # Main swap
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

@app.route('/')
def index():
    return render_template('index.html', pools=pools)

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
        
        return jsonify({
            'quote': output, 
            'formatted': formatted, 
            'pool_address': pool['address'],
            'fees': {
                'service_fee': service_fee,
                'service_rate': '0.25%',
                'pool_fee': '0.3%',
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
        min_out_nano = int(expected_out_nano * 0.99)
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
        
        print(f"[SUCCESS] Swap ready: {amount} {from_token} → ~{output:.6f} {to_token}")
        
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
                    'service_fee': f'{service_fee:.6f} {from_token} (0.25%)',
                    'pool_fee': f'{amount * 0.003:.6f} {from_token} (0.3%)',
                    'network_gas': f'{gas / 1e9:.3f} TON',
                }
            },
            'debug': {
                'expected_out': output,
                'min_out': min_out_nano / 10**pool['to_decimals'],
                'gas': gas / 1e9
            }
        })

    except Exception as e:
        print(f"[ERROR] Swap failed: {e}")
        import traceback
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
    app.run(debug=True)