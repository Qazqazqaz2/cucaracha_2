"""
Модуль для автоматического исполнения ордеров с реальным обменом через DEX
"""
import os
import time
from typing import Dict, Optional, Tuple
from decimal import Decimal
import traceback

from ton_rpc import (
    get_balance,
    validate_address,
    get_pool_reserves,
    get_expected_output,
    get_jetton_wallet
)
from dedust import create_swap_payload as dedust_create_swap_payload, DEDUST_GAS_AMOUNT
from stonfi import create_swap_payload as stonfi_create_swap_payload, STONFI_GAS_AMOUNT
from dotenv import load_dotenv

load_dotenv()

# Попытка импортировать pytoniq для отправки транзакций
try:
    from pytoniq import LiteClient, WalletV5R1, begin_cell
    from pytoniq.liteclient import LiteClientError
    PYTONIQ_AVAILABLE = True
except ImportError:
    PYTONIQ_AVAILABLE = False
    print("[ORDER EXECUTOR] pytoniq not available, transactions will be prepared but not sent")

order_wallet_mnemonic = "puzzle eager kit direct brief myth kid smooth spy valve struggle initial enroll champion girl sheriff flip radar always parent engine wing goddess grunt"

def to_nano(amount: float, currency: str = "ton") -> int:
    """Конвертация суммы в нано-единицы"""
    if currency != "ton":
        raise ValueError("Only TON supported")
    return int(amount * 1_000_000_000)


def calculate_quote_for_execution(from_amount: float, pool: dict, slippage: float = 1.0):
    """
    Рассчитывает выходное количество токенов для исполнения ордера
    
    Args:
        from_amount: Количество входных токенов
        pool: Информация о пуле (может быть обратным направлением)
        slippage: Проскальзывание в процентах
    
    Returns:
        tuple: (output_amount, min_out_nano, expected_out_nano)
    """
    try:
        reserve_from, reserve_to = get_pool_reserves(pool['address'])
        
        if reserve_from == 0 or reserve_to == 0:
            return 0, 0, 0
        
        # Определяем, какое направление используем
        # Если pool['from_token'] это первый токен в пуле, используем резервы как есть
        # Иначе нужно поменять местами резервы
        
        # Для упрощения: всегда используем резервы в том порядке, как они возвращаются
        # и считаем, что первый резерв соответствует from_token пула
        # Если направление обратное, нужно поменять резервы местами
        
        # Проверяем, соответствует ли направление пула реальным резервам
        # Для TON-USDT пула: reserve_from обычно TON, reserve_to обычно USDT
        # Если pool['from_token'] == 'TON', используем как есть
        # Если pool['from_token'] == 'USDT', меняем местами
        
        use_reverse = False
        # Упрощенная логика: если from_token пула это не TON, возможно нужно обратить
        # Но для точности лучше использовать get_expected_output из ton_rpc
        
        # Расчет через формулу AMM
        input_amount_raw = int(from_amount * 10**pool['from_decimals'])
        if input_amount_raw <= 0:
            return 0, 0, 0
        
        # Комиссия пула (обычно 0.3%)
        pool_fee = 0.003
        amount_in_with_fee = input_amount_raw * (1 - pool_fee)
        
        if use_reverse:
            numerator = amount_in_with_fee * reserve_from
            denominator = reserve_to + amount_in_with_fee
        else:
            numerator = amount_in_with_fee * reserve_to
            denominator = reserve_from + amount_in_with_fee
        
        if denominator == 0:
            return 0, 0, 0
        
        output_amount_raw = numerator // denominator
        output = output_amount_raw / 10**pool['to_decimals']
        
        expected_out_nano = int(output * 10**pool['to_decimals'])
        min_out_nano = int(expected_out_nano * (1 - slippage / 100))
        
        return output, min_out_nano, expected_out_nano
    except Exception as e:
        print(f"[ORDER EXECUTOR] Quote calculation error: {e}")
        traceback.print_exc()
        return 0, 0, 0


def determine_swap_direction(order: Dict, pool: Dict) -> Tuple[str, str, str, str]:
    """
    Определяет направление обмена для ордера
    
    Args:
        order: Данные ордера
        pool: Данные пула
    
    Returns:
        tuple: (from_token, to_token, from_token_address, swap_description)
    """
    order_type = order.get('type', '').lower()
    action = order.get('action', 'open').lower()  # 'open' или 'close'
    
    # Определяем базовое направление пула
    pool_from = pool.get('from_token', 'TON')
    pool_to = pool.get('to_token', 'USDT')
    
    if action == 'open':
        # Открытие позиции
        if order_type == 'long':
            # LONG: покупаем USDT за TON
            from_token = pool_from  # TON
            to_token = pool_to      # USDT
            from_token_address = pool.get('from_token_address', '')
            description = f"Открытие LONG: {from_token} -> {to_token}"
        elif order_type == 'short':
            # SHORT: продаем TON за USDT
            from_token = pool_from  # TON  
            to_token = pool_to      # USDT
            from_token_address = pool.get('from_token_address', '')
            description = f"Открытие SHORT: {from_token} -> {to_token}"
        else:
            # По умолчанию: TON -> USDT
            from_token = pool_from
            to_token = pool_to
            from_token_address = pool.get('from_token_address', '')
            description = f"Покупка: {from_token} -> {to_token}"
    else:
        # Закрытие позиции
        if order_type == 'long':
            # Закрытие LONG: продаем USDT, покупаем TON
            from_token = pool_to      # USDT
            to_token = pool_from      # TON
            from_token_address = pool.get('to_token_address', '')
            description = f"Закрытие LONG: {from_token} -> {to_token}"
        elif order_type == 'short':
            # Закрытие SHORT: покупаем TON, продаем USDT
            from_token = pool_to      # USDT
            to_token = pool_from      # TON
            from_token_address = pool.get('to_token_address', '')
            description = f"Закрытие SHORT: {from_token} -> {to_token}"
        else:
            # По умолчанию обратное направление
            from_token = pool_to
            to_token = pool_from
            from_token_address = pool.get('to_token_address', '')
            description = f"Продажа: {from_token} -> {to_token}"
    
    return from_token, to_token, from_token_address, description


async def send_transaction_async(wallet, dest_address: str, amount: int, payload: str):
    """
    Асинхронная отправка транзакции
    """
    try:
        from pytoniq import begin_cell
        import base64
        
        print(f"[ORDER EXECUTOR] Декодирование payload...")
        # Декодируем payload обратно в Cell
        payload_bytes = base64.b64decode(payload)
        from pytoniq_core import Cell
        payload_cell = Cell.from_boc(payload_bytes)[0]
        print(f"[ORDER EXECUTOR] ✅ Payload декодирован")
        
        # Отправляем транзакцию
        print(f"[ORDER EXECUTOR] Вызов wallet.transfer()...")
        result = await wallet.transfer(
            destination=dest_address,
            amount=amount,
            body=payload_cell
        )
        
        print(f"[ORDER EXECUTOR] ✅ Transaction sent successfully!")
        print(f"[ORDER EXECUTOR] Transaction result: {result}")
        
        return True
    except Exception as e:
        print(f"[ORDER EXECUTOR] ❌ Transaction error: {e}")
        print(f"[ORDER EXECUTOR] Error type: {type(e).__name__}")
        traceback.print_exc()
        return False


def execute_order_swap(order: Dict, pool: Dict, order_wallet_address: str, 
                       order_wallet_mnemonic: Optional[str] = None,
                       slippage: float = 1.0) -> Dict:
    """
    Выполняет реальный обмен при срабатывании ордера
    """
    try:
        order_id = order.get('id', 'unknown')
        order_type = order.get('type', '').lower()
        order_amount = float(order.get('amount', 0))
        action = order.get('action', 'open').lower()
        
        print(f"[ORDER EXECUTOR] Executing swap for order {order_id} (type: {order_type}, action: {action}, amount: {order_amount})")
        
        # Определяем направление обмена
        from_token, to_token, from_token_address, description = determine_swap_direction(order, pool)
        
        print(f"[ORDER EXECUTOR] {description}")
        
        # Проверяем баланс входного токена
        if from_token == "TON":
            # Используем TON
            amount_nano = int(order_amount * 10**9)
            
            # Проверяем баланс TON
            ton_balance = get_balance(order_wallet_address)
            required_ton = order_amount + 0.5  # +0.5 для газа
            print(f"[ORDER EXECUTOR] Баланс TON: {ton_balance:.6f}, требуется: {required_ton:.6f}")
            
            if ton_balance < required_ton:
                return {
                    'success': False,
                    'error': f'Недостаточно TON на кошельке ордеров. Баланс: {ton_balance:.6f}, требуется: {required_ton:.6f}'
                }
        else:
            # Если нужно продать Jetton, проверяем баланс
            if not from_token_address:
                return {
                    'success': False,
                    'error': f'Адрес токена {from_token} не найден в конфигурации пула'
                }
            
            jetton_wallet = get_jetton_wallet(from_token_address, order_wallet_address)
            jetton_balance = get_balance(jetton_wallet, decimals=pool.get('to_decimals', 6))
            
            print(f"[ORDER EXECUTOR] Баланс {from_token}: {jetton_balance:.6f}, требуется: {order_amount:.6f}")
            
            if jetton_balance < order_amount:
                return {
                    'success': False,
                    'error': f'Недостаточно {from_token} на кошельке ордеров. Баланс: {jetton_balance:.6f}, требуется: {order_amount:.6f}'
                }
            
            amount_nano = int(order_amount * 10**pool.get('to_decimals', 6))
        
        # Определяем правильное направление для расчета
        if action == 'open':
            # Прямой обмен: TON -> USDT
            calculation_pool = pool
            from_decimals = pool.get('from_decimals', 9)
            to_decimals = pool.get('to_decimals', 6)
        else:
            # Обратный обмен: USDT -> TON
            calculation_pool = {
                'address': pool['address'],
                'from_token': pool['to_token'],  # USDT
                'to_token': pool['from_token'],  # TON
                'from_decimals': pool.get('to_decimals', 6),
                'to_decimals': pool.get('from_decimals', 9),
                'dex': pool.get('dex', 'DeDust')
            }
            from_decimals = pool.get('to_decimals', 6)
            to_decimals = pool.get('from_decimals', 9)
        
        # Используем get_expected_output для точного расчета
        try:
            from_token_addr = calculation_pool.get('from_token_address') or os.environ.get("TON_AS_TOKEN")
            expected_out_nano = get_expected_output(
                calculation_pool['address'], 
                amount_nano, 
                from_token_addr
            )
            
            if expected_out_nano > 0:
                output = expected_out_nano / 10**to_decimals
                min_out_nano = int(expected_out_nano * (1 - slippage / 100))
                print(f"[ORDER EXECUTOR] Расчет через get_expected_output: {amount_nano/10**from_decimals:.6f} {from_token} -> {output:.6f} {to_token}")
            else:
                # Fallback на расчет через формулу
                output, min_out_nano, expected_out_nano = calculate_quote_for_execution(
                    order_amount, calculation_pool, slippage
                )
                print(f"[ORDER EXECUTOR] Расчет через формулу: {order_amount:.6f} {from_token} -> {output:.6f} {to_token}")
        except Exception as e:
            print(f"[ORDER EXECUTOR] Error using get_expected_output: {e}, using fallback")
            # Fallback на расчет через формулу
            output, min_out_nano, expected_out_nano = calculate_quote_for_execution(
                order_amount, calculation_pool, slippage
            )
            print(f"[ORDER EXECUTOR] Расчет через формулу (fallback): {order_amount:.6f} {from_token} -> {output:.6f} {to_token}")
        
        if output == 0 or min_out_nano == 0:
            return {
                'success': False,
                'error': 'Не удалось рассчитать выходное количество токенов'
            }
        
        # Определяем DEX и адреса
        dex = pool.get('dex', 'DeDust')
        
        if from_token == "TON":
            if dex == "DeDust":
                dest_addr = os.environ.get("DEDUST_NATIVE_VAULT")
                gas = DEDUST_GAS_AMOUNT
            elif dex == "StonFi":
                dest_addr = os.environ.get("STONFI_PROXY_TON")
                gas = STONFI_GAS_AMOUNT
            else:
                return {'success': False, 'error': f'Unsupported DEX: {dex}'}
            total_amount = amount_nano + gas
        else:
            # Для Jetton нужно использовать jetton wallet
            dest_addr = get_jetton_wallet(from_token_address, order_wallet_address)
            gas = to_nano(0.2)
            total_amount = gas
        
        dest_valid = validate_address(dest_addr)
        
        # Создаем payload для swap
        if dex == "DeDust":
            payload = dedust_create_swap_payload(
                pool['address'], order_wallet_address, amount_nano, min_out_nano, from_token
            )
        elif dex == "StonFi":
            payload = stonfi_create_swap_payload(
                pool['address'], order_wallet_address, amount_nano, min_out_nano, from_token
            )
        else:
            return {'success': False, 'error': f'Unsupported DEX: {dex}'}
        
        result = {
            'success': True,
            'order_id': order_id,
            'description': description,
            'transaction': {
                'address': dest_valid,
                'amount': str(total_amount),
                'payload': payload,
                'validUntil': int(time.time()) + 300
            },
            'swap_details': {
                'from_token': from_token,
                'to_token': to_token,
                'from_amount': order_amount,
                'expected_output': output,
                'min_output': min_out_nano / 10**to_decimals,
                'slippage': slippage,
                'gas': gas / 1e9
            }
        }
        
        # Если есть мнемоника и pytoniq доступен, отправляем транзакцию автоматически
        print(f"[ORDER EXECUTOR] Проверка условий для отправки транзакции:")
        print(f"  - PYTONIQ_AVAILABLE: {PYTONIQ_AVAILABLE}")
        print(f"  - order_wallet_mnemonic: {'установлена' if order_wallet_mnemonic else 'НЕ УСТАНОВЛЕНА'}")
        
        if order_wallet_mnemonic and PYTONIQ_AVAILABLE:
            try:
                import asyncio
                
                # Проверяем баланс перед отправкой
                if from_token == "TON":
                    balance = get_balance(order_wallet_address)
                    required = (total_amount / 1e9)
                    print(f"[ORDER EXECUTOR] Баланс кошелька: {balance:.6f} TON")
                    print(f"[ORDER EXECUTOR] Требуется: {required:.6f} TON")
                    
                    if balance < required:
                        result['transaction_sent'] = False
                        result['message'] = f'Недостаточно средств: баланс {balance:.6f} TON, требуется {required:.6f} TON'
                        print(f"[ORDER EXECUTOR] ❌ {result['message']}")
                        return result
                
                async def send_tx():
                    # Подключаемся к сети
                    testnet = os.environ.get("TESTNET", "False") == "True"
                    print(f"[ORDER EXECUTOR] Подключение к {'testnet' if testnet else 'mainnet'}...")
                    
                    if testnet:
                        client = LiteClient.from_testnet_config(0, trust_level=2)
                        network_global_id = 0  # testnet
                    else:
                        client = LiteClient.from_mainnet_config(0, trust_level=2)
                        network_global_id = -239  # mainnet
                    
                    await client.connect()
                    print(f"[ORDER EXECUTOR] ✅ Подключено к сети")
                    
                    # Загружаем кошелек с указанием network_global_id
                    print(f"[ORDER EXECUTOR] Загрузка кошелька из мнемоники...")
                    try:
                        wallet = await WalletV5R1.from_mnemonic(
                            client, 
                            order_wallet_mnemonic.split(),
                            network_global_id=network_global_id
                        )
                    except Exception as e:
                        print(f"[ORDER EXECUTOR] Попытка с network_global_id не удалась: {e}")
                        # Попробуем с wallet_id
                        wallet = await WalletV5R1.from_mnemonic(
                            client, 
                            order_wallet_mnemonic.split(),
                            wallet_id=698983191
                        )
                    
                    # Получаем адрес кошелька (исправленная строка)
                    wallet_address = str(wallet.address)
                    print(f"[ORDER EXECUTOR] ✅ Кошелек загружен: {wallet_address}")
                    
                    # Проверяем, что адрес кошелька совпадает
                    if wallet_address != order_wallet_address:
                        print(f"[ORDER EXECUTOR] ⚠️  ВНИМАНИЕ: Адрес кошелька из мнемоники ({wallet_address}) не совпадает с order_wallet_address ({order_wallet_address})")
                    
                    # Отправляем транзакцию
                    print(f"[ORDER EXECUTOR] Отправка транзакции...")
                    print(f"  - Адрес получателя: {dest_valid}")
                    print(f"  - Сумма: {total_amount / 1e9:.9f} TON")
                    print(f"  - Payload length: {len(payload)} байт")
                    
                    success = await send_transaction_async(wallet, dest_valid, total_amount, payload)
                    await client.close()
                    
                    if success:
                        print(f"[ORDER EXECUTOR] ✅ Транзакция успешно отправлена!")
                    else:
                        print(f"[ORDER EXECUTOR] ❌ Ошибка при отправке транзакции")
                    
                    return success
                
                # Запускаем асинхронную отправку
                print(f"[ORDER EXECUTOR] Запуск асинхронной отправки транзакции...")
                sent = asyncio.run(send_tx())
                result['transaction_sent'] = sent
                if sent:
                    result['message'] = 'Транзакция отправлена в блокчейн'
                    print(f"[ORDER EXECUTOR] ✅ {result['message']}")
                else:
                    result['message'] = 'Ошибка при отправке транзакции'
                    print(f"[ORDER EXECUTOR] ❌ {result['message']}")
            except Exception as e:
                print(f"[ORDER EXECUTOR] ❌ Auto-send error: {e}")
                import traceback
                traceback.print_exc()
                result['transaction_sent'] = False
                result['message'] = f'Транзакция подготовлена, но не отправлена: {e}'
        else:
            result['transaction_sent'] = False
            if not PYTONIQ_AVAILABLE:
                result['message'] = 'Транзакция подготовлена (pytoniq не установлен)'
                print(f"[ORDER EXECUTOR] ⚠️  {result['message']}")
            else:
                result['message'] = 'Транзакция подготовлена (мнемоника не указана)'
                print(f"[ORDER EXECUTOR] ⚠️  {result['message']}")
                print(f"[ORDER EXECUTOR] 💡 Для автоматической отправки транзакций установите ORDER_WALLET_MNEMONIC в .env")
        
        print(f"[ORDER EXECUTOR] Swap prepared: {order_amount} {from_token} -> ~{output:.6f} {to_token}")
        return result
        
    except Exception as e:
        print(f"[ORDER EXECUTOR] Error executing swap: {e}")
        traceback.print_exc()
        return {
            'success': False,
            'error': str(e)
        }