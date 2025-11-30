import os
import time
import asyncio
import base64
from typing import Dict, Optional, Tuple
from decimal import Decimal
import traceback

from ton_rpc import (
    get_balance,
    validate_address,
    get_pool_reserves,
    get_expected_output,
    get_jetton_wallet,
    get_jetton_wallet_balance,
    estimate_gas_fee
)
from dedust import create_swap_payload as dedust_create_swap_payload, DEDUST_GAS_AMOUNT
from stonfi import create_swap_payload as stonfi_create_swap_payload, STONFI_GAS_AMOUNT
from dotenv import load_dotenv

# Import the new network configuration
try:
    from network_config import connect_with_retry, create_lite_client
    NETWORK_CONFIG_AVAILABLE = True
except ImportError:
    NETWORK_CONFIG_AVAILABLE = False
    connect_with_retry = None
    create_lite_client = None

from pytoniq_core import Address

if not NETWORK_CONFIG_AVAILABLE:
    print("[ORDER EXECUTOR] Network config not available, using fallback")

load_dotenv()

TRANSIENT_ERROR_KEYWORDS = (
    'jetton wallet',
    'ton rpc',
    'server error',
    'jsonrpc',
    'timeout',
    'rungetmethod'
)


def _is_transient_error(message: str) -> bool:
    if not message:
        return False
    msg = message.lower()
    return any(keyword in msg for keyword in TRANSIENT_ERROR_KEYWORDS)


def _error_result(message: str, transient: Optional[bool] = None):
    if transient is None:
        transient = _is_transient_error(message)
    return {'success': False, 'error': message, 'transient': transient}

from pytoniq import LiteClient, WalletV5R1
PYTONIQ_AVAILABLE = True


def to_nano(amount: float, decimals: int = 9) -> int:
    """Конвертация суммы в минимальные единицы"""
    return int(amount * (10 ** decimals))


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
        
        input_amount_raw = int(from_amount * 10**pool['from_decimals'])
        if input_amount_raw <= 0:
            return 0, 0, 0
        
        # Комиссия пула (обычно 0.3%)
        pool_fee = 0.003
        amount_in_with_fee = input_amount_raw * (1 - pool_fee)
        
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
            # LONG: покупаем TON за USDT
            from_token = pool_to  # USDT
            to_token = pool_from  # TON
            from_token_address = pool.get('to_token_address', '')
            description = f"Открытие LONG: {from_token} -> {to_token}"
        elif order_type == 'short':
            # SHORT: продаем TON за USDT
            from_token = pool_from  # TON
            to_token = pool_to      # USDT
            from_token_address = pool.get('from_token_address', '')
            description = f"Открытие SHORT: {from_token} -> {to_token}"
        else:
            # По умолчанию: USDT -> TON
            from_token = pool_to
            to_token = pool_from
            from_token_address = pool.get('to_token_address', '')
            description = f"Покупка: {from_token} -> {to_token}"
    else:
        # Закрытие позиции
        if order_type == 'long':
            # Закрытие LONG: продаем TON, покупаем USDT
            from_token = pool_from  # TON
            to_token = pool_to      # USDT
            from_token_address = pool.get('from_token_address', '')
            description = f"Закрытие LONG: {from_token} -> {to_token}"
        elif order_type == 'short':
            # Закрытие SHORT: покупаем TON, продаем USDT
            from_token = pool_to    # USDT
            to_token = pool_from    # TON
            from_token_address = pool.get('to_token_address', '')
            description = f"Закрытие SHORT: {from_token} -> {to_token}"
        else:
            # По умолчанию прямое направление
            from_token = pool_from
            to_token = pool_to
            from_token_address = pool.get('from_token_address', '')
            description = f"Продажа: {from_token} -> {to_token}"
    
    return from_token, to_token, from_token_address, description


async def send_transaction_async(wallet, dest_address: str, amount: int, payload: Optional[str] = None):
    """
    Асинхронная отправка транзакции с проверкой инициализации кошелька
    """
    try:
        # Проверяем, инициализирован ли кошелек
        print(f"[ORDER EXECUTOR] Проверка состояния кошелька...")
        try:
            state = await wallet.get_state()
            print(f"[ORDER EXECUTOR] Состояние кошелька: {state}")
        except Exception as state_error:
            print(f"[ORDER EXECUTOR] Ошибка проверки состояния: {state_error}")
            # Пытаемся проверить через get_seqno
            try:
                seqno = await wallet.get_seqno()
                print(f"[ORDER EXECUTOR] Кошелек инициализирован, seqno: {seqno}")
            except Exception as seqno_error:
                print(f"[ORDER EXECUTOR] Кошелек не инициализирован: {seqno_error}")
                return False
        
        payload_cell = None
        if payload:
            print(f"[ORDER EXECUTOR] Декодирование payload...")
            payload_bytes = base64.b64decode(payload)
            from pytoniq_core import Cell
            payload_cell = Cell.from_boc(payload_bytes)[0]
            print(f"[ORDER EXECUTOR] ✅ Payload декодирован")
        
        # Отправляем транзакцию
        print(f"[ORDER EXECUTOR] Вызов wallet.transfer()...")
        transfer_kwargs = {
            'destination': dest_address,
            'amount': amount,
        }
        if payload_cell:
            transfer_kwargs['body'] = payload_cell
        
        result = await wallet.transfer(**transfer_kwargs)
        
        print(f"[ORDER EXECUTOR] ✅ Transaction sent successfully!")
        print(f"[ORDER EXECUTOR] Transaction result: {result}")
        
        return True
    except Exception as e:
        print(f"[ORDER EXECUTOR] ❌ Transaction error: {e}")
        print(f"[ORDER EXECUTOR] Error type: {type(e).__name__}")
        traceback.print_exc()
        return False

async def initialize_wallet_if_needed(wallet, client):
    """
    Инициализирует кошелек, если он не развернут
    """
    try:
        # Пытаемся получить seqno - если получится, кошелек инициализирован
        seqno = await wallet.get_seqno()
        print(f"[ORDER EXECUTOR] Кошелек уже инициализирован, seqno: {seqno}")
        return True
    except Exception as e:
        print(f"[ORDER EXECUTOR] Кошелек не инициализирован: {e}")
        print(f"[ORDER EXECUTOR] Для инициализации отправьте 0.05 TON на адрес: {wallet.address.to_str()}")
        print(f"[ORDER EXECUTOR] Или инициализируйте через: https://ton.org/docs/develop/smart-contracts/tutorials/wallet")
        return False

async def deploy_wallet_v5(wallet):
    """
    Развертывает кошелек V5 через внутреннюю транзакцию
    """
    try:
        from pytoniq_core import Builder
        
        # Создаем сообщение для развертывания
        builder = Builder()
        builder.store_uint(0, 32)  # op
        builder.store_uint(0, 64)  # query_id
        
        # Отправляем транзакцию развертывания
        result = await wallet.raw_transfer(
            messages=[wallet.create_wallet_internal_message(
                destination=wallet.address,
                value=100000000,  # 0.1 TON для развертывания
                body=builder.end_cell()
            )]
        )
        
        print(f"[ORDER EXECUTOR] ✅ Кошелек развернут: {result}")
        return True
    except Exception as e:
        print(f"[ORDER EXECUTOR] ❌ Ошибка развертывания кошелька: {e}")
        return False

def _maybe_send_transaction(order_wallet_address: str, order_wallet_mnemonic: Optional[str],
                            dest_address: str, amount: int, payload: Optional[str] = None):
    """
    Запускает отправку транзакции с проверкой инициализации кошелька
    """
    result = {
        'transaction_sent': False,
        'message': 'pytoniq is not available or mnemonic missing',
        'transaction': {
            'address': dest_address,
            'amount': str(amount),
            'payload': payload
        },
        'transient': False
    }
    
    if not order_wallet_mnemonic:
        result['message'] = 'Order wallet mnemonic is not provided'
        return result
    
    # Validate that the mnemonic is not empty or just whitespace
    if not order_wallet_mnemonic.strip():
        result['message'] = 'Order wallet mnemonic is empty or invalid'
        return result
    
    if not PYTONIQ_AVAILABLE:
        result['message'] = 'pytoniq package is not installed on server'
        return result
    
    async def send_tx():
        testnet = os.environ.get("TESTNET", "False") == "True"
        print(f"[ORDER EXECUTOR] Подключение к {'testnet' if testnet else 'mainnet'}...")
        
        # Use the new network config function
        if NETWORK_CONFIG_AVAILABLE and create_lite_client:
            client = create_lite_client(testnet)
        else:
            # Fallback to direct creation
            try:
                from pytoniq import LiteClient
                if testnet:
                    client = LiteClient.from_testnet_config(ls_i=1)
                else:
                    client = LiteClient.from_mainnet_config(ls_i=1)
            except Exception as e:
                print(f"[ORDER EXECUTOR] Failed to create client: {e}")
                result['message'] = 'Failed to create LiteClient'
                return False
        
        if not client:
            result['message'] = 'Failed to create LiteClient'
            return False
        
        try:
            # Connect with retry logic
            if NETWORK_CONFIG_AVAILABLE and connect_with_retry:
                if not await connect_with_retry(client):
                    result['message'] = 'Failed to connect to TON network'
                    return False
            else:
                # Fallback connection
                try:
                    await client.connect()
                except Exception as e:
                    print(f"[ORDER EXECUTOR] Connection failed: {e}")
                    result['message'] = 'Failed to connect to TON network'
                    return False
            
            # Get network global ID
            network_global_id = -239 if not testnet else 0
            
            # Validate mnemonic format
            mnemonic_words = order_wallet_mnemonic.strip().split()
            if len(mnemonic_words) < 12:
                result['message'] = 'Invalid mnemonic: must contain at least 12 words'
                await client.close()
                return False
            
            wallet = await WalletV5R1.from_mnemonic(
                provider=client,
                mnemonics=mnemonic_words,
                wallet_id=2147483409,  # Standard wallet ID
                network_global_id=network_global_id
            )
            
            wallet_address_from_mnemonic = wallet.address.to_str(is_bounceable=True, is_url_safe=True)
            print(f"[ORDER EXECUTOR] Адрес из мнемоники: {wallet_address_from_mnemonic}")
            print(f"[ORDER EXECUTOR] Ожидаемый адрес: {order_wallet_address}")
            
            # Check if wallet addresses match
            if wallet_address_from_mnemonic != order_wallet_address:
                print(f"[ORDER EXECUTOR] ⚠️  Предупреждение: Адрес из мнемоники не совпадает с ожидаемым адресом!")
                print(f"[ORDER EXECUTOR] Это может привести к отправке средств на неправильный кошелек.")
                # For security reasons, we should not proceed with the transaction if addresses don't match
                result['message'] = f'Адрес кошелька из мнемоники ({wallet_address_from_mnemonic}) не совпадает с ожидаемым адресом ({order_wallet_address}). Отправка транзакции заблокирована для безопасности.'
                print(f"[ORDER EXECUTOR] {result['message']}")
                await client.close()
                return False
            
            # Check if wallet is initialized by trying to get seqno
            wallet_initialized = False
            try:
                seqno = await wallet.get_seqno()
                wallet_initialized = True
            except Exception as seqno_error:
                print(f"[ORDER EXECUTOR] Кошелек не инициализирован: {seqno_error}")
                wallet_initialized = False
                # Even if not initialized, we can still check balance via RPC
                wallet_balance = get_balance(order_wallet_address)
                print(f"[ORDER EXECUTOR] Баланс кошелька (через RPC): {wallet_balance:.6f} TON")
                
                if wallet_balance >= 0.1:  # 0.1 TON for deployment
                    print(f"[ORDER EXECUTOR] Кошелек имеет средства для развертывания")
                    # For uninitialized wallets with funds, we should still attempt the transaction
                    # The first transaction will automatically deploy the wallet
                else:
                    result['message'] = f'Кошелек не инициализирован и недостаточно средств для развертывания. Баланс: {wallet_balance:.6f} TON, требуется: 0.1 TON'
                    print(f"[ORDER EXECUTOR] {result['message']}")
                    await client.close()
                    return False
            
            # Check balance using direct RPC method (more reliable)
            wallet_balance = get_balance(order_wallet_address)
            required_ton = amount / 1e9 + 0.05  # amount + gas buffer
            
            print(f"[ORDER EXECUTOR] Баланс кошелька: {wallet_balance:.6f} TON")
            print(f"[ORDER EXECUTOR] Требуется: {required_ton:.6f} TON")
            
            if wallet_balance < required_ton:
                result['message'] = f'Недостаточно средств. Баланс: {wallet_balance:.6f} TON, требуется: {required_ton:.6f} TON'
                print(f"[ORDER EXECUTOR] {result['message']}")
                await client.close()
                return False
            
            # Prepare payload if exists
            payload_cell = None
            if payload:
                try:
                    payload_bytes = base64.b64decode(payload)
                    from pytoniq_core import Cell
                    payload_cell = Cell.from_boc(payload_bytes)[0]
                    print(f"[ORDER EXECUTOR] Payload подготовлен")
                except Exception as payload_error:
                    print(f"[ORDER EXECUTOR] Ошибка подготовки payload: {payload_error}")
                    await client.close()
                    return False
            
            # Send transaction
            print(f"[ORDER EXECUTOR] Отправка транзакции...")
            try:
                # For uninitialized wallets, the first transaction will deploy the wallet automatically
                if payload_cell:
                    transfer_result = await wallet.transfer(
                        destination=dest_address,
                        amount=amount,
                        body=payload_cell
                    )
                else:
                    transfer_result = await wallet.transfer(
                        destination=dest_address,
                        amount=amount
                    )
                
                print(f"[ORDER EXECUTOR] ✅ Транзакция отправлена успешно!")
                await client.close()
                return True
                
            except Exception as transfer_error:
                print(f"[ORDER EXECUTOR] ❌ Ошибка отправки транзакции: {transfer_error}")
                # If it's an initialization error, provide more specific guidance
                error_str = str(transfer_error).lower()
                if "contract is not initialized" in error_str or "not initialized" in error_str:
                    print(f"[ORDER EXECUTOR] 💡 Кошелек требует инициализации. Первый перевод TON на этот адрес автоматически инициализирует контракт.")
                await client.close()
                return False
            
        except Exception as e:
            print(f"[ORDER EXECUTOR] Ошибка: {e}")
            try:
                if client:
                    await client.close()
            except Exception:
                pass
            return False
    
    try:
        success = asyncio.run(send_tx())
        result['transaction_sent'] = success
        if success:
            result['message'] = 'Transaction sent successfully'
        return result
    except Exception as e:
        print(f"[ORDER EXECUTOR] ❌ Ошибка отправки транзакции: {e}")
        traceback.print_exc()
        result['message'] = str(e)
        result['transient'] = _is_transient_error(result['message'])
        return result


def calculate_order_gas_requirements(order: Dict, pool: Dict) -> Dict:
    """
    Рассчитывает необходимое количество газа для ордера
    """
    try:
        order_amount = float(order.get('amount', 0))
        slippage = float(order.get('max_slippage', 1.0))
        
        # Определяем направление обмена
        from_token, to_token, from_token_address, description = determine_swap_direction(order, pool)
        
        # Определяем decimals
        from_decimals = 9 if from_token == "TON" else 6
        to_decimals = 6 if to_token == "USDT" else 9
        
        # Определяем, нужно ли обратить пул для расчета
        calculation_pool = pool
        if from_token == pool.get('to_token', 'USDT'):
            calculation_pool = {
                'address': pool['address'],
                'from_token': pool['to_token'],
                'to_token': pool['from_token'],
                'from_token_address': pool.get('to_token_address'),
                'to_token_address': pool.get('from_token_address'),
                'from_decimals': pool.get('to_decimals', 6),
                'to_decimals': pool.get('from_decimals', 9),
                'dex': pool.get('dex', 'DeDust')
            }
        
        # Рассчитываем выходное количество токенов
        output, min_out_nano, expected_out_nano = calculate_quote_for_execution(
            order_amount, calculation_pool, slippage
        )
        
        if output == 0 or min_out_nano == 0:
            return {
                'success': False,
                'error': 'Не удалось рассчитать выходное количество токенов'
            }
        
        # Определяем DEX и базовый газ
        dex = pool.get('dex', 'DeDust')
        
        # РЕАЛЬНЫЕ РАСЧЕТЫ ГАЗА:
        # Для DeDust: ~0.15 TON, для StonFi: ~0.12 TON
        if dex == "DeDust":
            base_gas = to_nano(0.15, 9)  # 0.15 TON для DeDust
        elif dex == "StonFi":
            base_gas = to_nano(0.12, 9)  # 0.12 TON для StonFi
        else:
            base_gas = to_nano(0.15, 9)  # fallback значение
        
        # Дополнительный газ для комиссий обменника
        exchange_fee_gas = to_nano(0.05, 9)  # 0.05 TON для комиссий
        
        # Комиссия обменника (0.3% pool fee + 0.25% service fee = 0.55%)
        exchange_fee_percent = 0.0055  # 0.55%
        exchange_fee_amount = order_amount * exchange_fee_percent
        
        # Общий газ
        total_gas = base_gas + exchange_fee_gas
        
        # Рассчитываем общую сумму (для TON + газ)
        total_amount_ton = 0
        if from_token == "TON":
            # Для TON: сумма ордера + газ
            total_amount_ton = order_amount + (total_gas / 1e9)
        else:
            # Для Jetton: только газ
            total_amount_ton = total_gas / 1e9
        
        return {
            'success': True,
            'gas_amount': total_gas / 1e9,  # в TON
            'base_gas': base_gas / 1e9,  # базовый газ
            'exchange_fee_gas': exchange_fee_gas / 1e9,  # газ для комиссий
            'exchange_fee_percent': exchange_fee_percent * 100,  # процент комиссии
            'exchange_fee_amount': exchange_fee_amount,  # сумма комиссии в from_token
            'total_amount': total_amount_ton,  # в TON (сумма + газ)
            'from_token': from_token,
            'to_token': to_token,
            'from_amount': order_amount,
            'expected_output': output,
            'dex': dex,
            'description': description
        }
    except Exception as e:
        print(f"[ORDER EXECUTOR] Ошибка расчета газа: {e}")
        traceback.print_exc()
        return {
            'success': False,
            'error': str(e)
        }


def _estimate_dynamic_gas(wallet_address: str, payload: str, fallback: int) -> int:
    """
    Оценка газа через RPC с резервным значением.
    """
    try:
        fees = estimate_gas_fee(wallet_address, payload) if payload else None
        if not fees:
            return fallback
        total = fees.get('total_fee') or 0
        if not total:
            total = fees.get('gas_fee', 0) + fees.get('fwd_fee', 0) + fees.get('in_fwd_fee', 0)
        buffered = int(total * 1.2) + to_nano(0.02, 9)
        return max(buffered, fallback)
    except Exception as e:
        print(f"[ORDER EXECUTOR] Gas estimation fallback: {e}")
        return fallback


def build_comment_payload(message: str) -> Optional[str]:
    """
    Создает payload с текстовым комментарием для простых переводов TON.
    """
    if not message:
        return None
    from pytoniq_core.boc import Builder
    builder = Builder()
    builder.store_uint(0, 32)
    builder.store_uint(0, 64)
    builder.store_bytes(message.encode('utf-8'))
    return base64.b64encode(builder.end_cell().to_boc()).decode('utf-8')


def execute_order_swap(order: Dict, pool: Dict, wallet_credentials: Dict,
                       slippage: float = 1.0) -> Dict:
    """
    Выполняет реальный обмен при срабатывании ордера
    """
    try:
        order_id = order.get('id', 'unknown')
        order_type = order.get('type', '').lower()
        action = order.get('action', 'open').lower()
        order_amount = float(order.get('amount', 0))
        order_wallet_address = wallet_credentials.get('address')
        order_wallet_mnemonic = wallet_credentials.get('mnemonic')
        
        if not order_wallet_address:
            return {'success': False, 'error': 'Order wallet address is not specified'}
                
        # Определяем направление обмена
        from_token, to_token, from_token_address, description = determine_swap_direction(order, pool)
        
        print(f"[ORDER EXECUTOR] {description}")
        
        # Определяем decimals
        from_decimals = 9 if from_token == "TON" else 6
        to_decimals = 6 if to_token == "USDT" else 9
        
        # Определяем, нужно ли обратить пул для расчета
        calculation_pool = pool
        if from_token == pool.get('to_token', 'USDT'):
            calculation_pool = {
                'address': pool['address'],
                'from_token': pool['to_token'],
                'to_token': pool['from_token'],
                'from_token_address': pool.get('to_token_address'),
                'to_token_address': pool.get('from_token_address'),
                'from_decimals': pool.get('to_decimals', 6),
                'to_decimals': pool.get('from_decimals', 9),
                'dex': pool.get('dex', 'DeDust')
            }
        
        # Проверяем баланс входного токена
        if from_token == "TON":
            # Используем TON
            amount_nano = to_nano(order_amount, from_decimals)
            
            # Проверяем баланс TON с РЕАЛЬНЫМ расчетом газа
            ton_balance = get_balance(order_wallet_address)
            
            # РЕАЛЬНЫЙ расчет требуемого газа
            dex = pool.get('dex', 'DeDust')
            if dex == "DeDust":
                required_gas = 0.15  # TON
            elif dex == "StonFi":
                required_gas = 0.12  # TON
            else:
                required_gas = 0.15  # TON
                
            required_ton = order_amount + required_gas
            print(f"[ORDER EXECUTOR] Баланс TON: {ton_balance:.6f}, требуется: {order_amount:.6f} TON + {required_gas:.6f} TON газа = {required_ton:.6f} TON")
            
            if ton_balance < required_ton:
                return _error_result(
                    f'Недостаточно TON на кошельке ордеров. Баланс: {ton_balance:.6f}, требуется: {required_ton:.6f} TON (ордер: {order_amount:.6f} TON + газ: {required_gas:.6f} TON)',
                    transient=False
                )
        else:
            # Если нужно продать Jetton, проверяем баланс
            if not from_token_address:
                return _error_result(
                    f'Адрес токена {from_token} не найден в конфигурации пула',
                    transient=False
                )
            
            try:
                jetton_wallet = get_jetton_wallet(from_token_address, order_wallet_address)
            except ValueError as e:
                if "Empty response" in str(e):
                    return _error_result(str(e), transient=True)
                raise
            jetton_balance_raw = get_jetton_wallet_balance(jetton_wallet)
            jetton_balance = jetton_balance_raw / (10 ** from_decimals)
            
            print(f"[ORDER EXECUTOR] Баланс {from_token}: {jetton_balance:.6f}, требуется: {order_amount:.6f}")
            
            if jetton_balance < order_amount:
                return _error_result(
                    f'Недостаточно {from_token} на кошельке ордеров. Баланс: {jetton_balance:.6f}, требуется: {order_amount:.6f}',
                    transient=False
                )
            
            amount_nano = to_nano(order_amount, from_decimals)
            
            # Для Jetton также проверяем наличие TON для газа
            ton_balance = get_balance(order_wallet_address)
            required_gas = 0.15  # TON для Jetton операций
            if ton_balance < required_gas:
                return _error_result(
                    f'Недостаточно TON для газа. Баланс: {ton_balance:.6f}, требуется: {required_gas:.6f} TON',
                    transient=False
                )
        
        # Рассчитываем выходное количество токенов
        output, min_out_nano, expected_out_nano = calculate_quote_for_execution(
            order_amount, calculation_pool, slippage
        )
        print(f"[ORDER EXECUTOR] Расчет через формулу: {order_amount:.6f} {from_token} -> {output:.6f} {to_token}")
        
        if output == 0 or min_out_nano == 0:
            return _error_result('Не удалось рассчитать выходное количество токенов', transient=False)
        
        # Определяем DEX и адреса
        dex = pool.get('dex', 'DeDust')
        
        if from_token == "TON":
            if dex == "DeDust":
                dest_addr = os.environ.get("DEDUST_NATIVE_VAULT")
                base_gas = to_nano(0.15, 9)  # 0.15 TON для DeDust
            elif dex == "StonFi":
                dest_addr = os.environ.get("STONFI_PROXY_TON")
                base_gas = to_nano(0.12, 9)  # 0.12 TON для StonFi
            else:
                return _error_result(f'Unsupported DEX: {dex}', transient=False)
        else:
            # Для Jetton нужно использовать jetton wallet
            dest_addr = get_jetton_wallet(from_token_address, order_wallet_address)
            base_gas = to_nano(0.15, 9)  # 0.15 TON для Jetton операций
        
        # Validate address and make sure it's not None
        if dest_addr is None:
            return _error_result(f'Destination address is None for token {from_token}', transient=False)
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
            return _error_result(f'Unsupported DEX: {dex}', transient=False)
        
        # Используем РЕАЛЬНЫЙ газ вместо динамического расчета
        gas = base_gas
        
        if from_token == "TON":
            total_amount = amount_nano + gas
        else:
            total_amount = gas
        
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
                'min_output': min_out_nano / (10 ** to_decimals),
                'slippage': slippage,
                'gas': gas / 1e9,
                'exchange_fee_percent': 0.55,  # 0.55% комиссия
                'exchange_fee_amount': order_amount * 0.0055,  # сумма комиссии
                'net_received': output - (order_amount * 0.0055)  # чистая сумма после комиссий
            },
            'transient': False
        }
        
        if from_token == "TON":
            balance = get_balance(order_wallet_address)
            required = total_amount / 1e9
            print(f"[ORDER EXECUTOR] Баланс кошелька: {balance:.6f} TON, требуется: {required:.6f} TON (ордер: {order_amount:.6f} TON + газ: {gas/1e9:.6f} TON)")
            if balance < required:
                result['transaction_sent'] = False
                result['message'] = f'Недостаточно средств: баланс {balance:.6f} TON, требуется {required:.6f} TON'
                return result
        
        send_result = _maybe_send_transaction(order_wallet_address, order_wallet_mnemonic, dest_valid, total_amount, payload)
        result.update(send_result)
        print(f"[ORDER EXECUTOR] Swap prepared: {order_amount} {from_token} -> ~{output:.6f} {to_token} (комиссия: {order_amount * 0.0055:.6f} {from_token})")
        return result
        
    except Exception as e:
        print(f"[ORDER EXECUTOR] Error executing swap: {e}")
        traceback.print_exc()
        return _error_result(str(e))


def transfer_ton_from_wallet(wallet_credentials: Dict, destination: str,
                             amount_ton: float, comment: Optional[str] = None) -> Dict:
    """
    Простой перевод TON с кошелька ордеров.
    """
    wallet_address = wallet_credentials.get('address')
    wallet_mnemonic = wallet_credentials.get('mnemonic')
    if not wallet_address:
        return _error_result('Order wallet address is not specified', transient=False)
    if amount_ton <= 0:
        return {'success': False, 'error': 'Amount must be positive'}
    
    balance = get_balance(wallet_address)
    if balance < amount_ton:
        return {'success': False, 'error': f'Недостаточно средств: {balance:.4f} TON < {amount_ton:.4f} TON'}
    
    payload = build_comment_payload(comment) if comment else None
    amount_nano = to_nano(amount_ton, 9)
    dest_valid = validate_address(destination)
    send_result = _maybe_send_transaction(wallet_address, wallet_mnemonic, dest_valid, amount_nano, payload)
    return {
        'success': send_result.get('transaction_sent', False),
        'message': send_result.get('message'),
        'transaction': send_result.get('transaction')
    }


if __name__ == "__main__":
    # Тестовая функция для проверки расчета газа
    test_order = {
        'id': 'test_order_1',
        'type': 'long',
        'amount': 1.0,
        'max_slippage': 1.0,
        'order_wallet': 'UQD1V6ZNou__gvGZ9b-c69g9n1aXvSN4HJG1avp-AHDSRueL'
    }
    
    test_pool = {
        'address': 'EQD1V6ZNou__gvGZ9b-c69g9n1aXvSN4HJG1avp-AHDSRueL',
        'from_token': 'TON',
        'to_token': 'USDT',
        'from_token_address': '',
        'to_token_address': 'EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs',
        'from_decimals': 9,
        'to_decimals': 6,
        'dex': 'DeDust'
    }
    
    gas_info = calculate_order_gas_requirements(test_order, test_pool)
    print("Тестовый расчет газа:")
    print(gas_info)
