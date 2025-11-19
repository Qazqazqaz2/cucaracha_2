"""
Тестовый скрипт для проверки функционала ордеров
Позволяет протестировать открытие ордеров и исполнение по TP/SL без ожидания реальных цен
"""

import os
import sys
import json
from datetime import datetime
from decimal import Decimal

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Загружаем переменные окружения
from dotenv import load_dotenv
load_dotenv()

ORDER_WALLET_MNEMONIC = os.environ.get("ORDER_WALLET_MNEMONIC")
print(f"[TEST SETUP] ORDER_WALLET_MNEMONIC loaded: {'YES' if ORDER_WALLET_MNEMONIC else 'NO'}")
if ORDER_WALLET_MNEMONIC:
    print(f"[TEST SETUP] Mnemonic length: {len(ORDER_WALLET_MNEMONIC.split())} words")

# Импортируем функции из app.py
from app import (
    get_db_connection, 
    save_order, 
    load_orders,
    check_orders_execution,
    pools,
    DEFAULT_SLIPPAGE,
    order_wallet_address,
    ORDER_WALLET_MNEMONIC as APP_ORDER_WALLET_MNEMONIC  # импортируем из app
)

print(f"[TEST SETUP] ORDER_WALLET_MNEMONIC from app: {'YES' if APP_ORDER_WALLET_MNEMONIC else 'NO'}")

ORDER_WALLET_MNEMONIC = "puzzle eager kit direct brief myth kid smooth spy valve struggle initial enroll champion girl sheriff flip radar always parent engine wing goddess grunt"
def create_test_order(order_id: str, order_type: str = 'long', entry_price: float = 1.8, 
                     stop_loss: float = None, take_profit: float = None, 
                     current_price: float = 1.79, amount: float = 1.0):
    """
    Создает тестовый ордер в БД
    
    Args:
        order_id: Уникальный ID ордера
        order_type: 'long' или 'short'
        entry_price: Цена входа
        stop_loss: Цена стоп-лосса
        take_profit: Цена тейк-профита
        current_price: Текущая цена (для price_at_creation)
        amount: Количество TON
    """
    user_wallet = "EQC7RQVpFx9h4FCL2Yif-rNie9Z-W4qBkWbnkl75SkqEmc3Y"
    order_wallet = "UQD1V6ZNou__gvGZ9b-c69g9n1aXvSN4HJG1avp-AHDSRueL"
    
    order = {
        'id': order_id,
        'type': order_type,
        'pair': 'TON-USDT',
        'amount': amount,
        'entry_price': entry_price,
        'stop_loss': stop_loss,
        'take_profit': take_profit,
        'user_wallet': user_wallet,
        'order_wallet': order_wallet,
        'status': 'waiting_entry',
        'created_at': datetime.now().isoformat(),
        'funded_at': datetime.now().isoformat(),
        'price_at_creation': current_price,
        'max_slippage': DEFAULT_SLIPPAGE
    }
    
    save_order(order)
    print(f"✅ Создан тестовый ордер {order_id}: {order_type.upper()}, entry={entry_price}, SL={stop_loss}, TP={take_profit}")
    return order


def mock_get_current_price(pool_addr: str, pool: dict = None, mock_price: float = None):
    """
    Мок-функция для get_current_price, возвращает заданную цену
    """
    if mock_price is not None:
        return mock_price
    # Fallback на реальную функцию если mock_price не задан
    from app import get_current_price as real_get_current_price
    return real_get_current_price(pool_addr, pool)


def create_mock_execute_swap(use_real_mnemonic=False):
    """
    Создает мок-функцию для execute_order_swap с правильной сигнатурой
    
    Args:
        use_real_mnemonic: Если True, использует реальную мнемонику для тестирования отправки
    """
    def mock_execute_swap(order, pool, order_wallet_address, order_wallet_mnemonic=None, slippage=1.0):
        print(f"\n[ТЕСТ] Вызов execute_order_swap для ордера {order['id']}")
        print(f"[ТЕСТ] Параметры: {order['amount']} {order['type']}")
        print(f"[ТЕСТ] Переданная мнемоника: {'ДА' if order_wallet_mnemonic else 'НЕТ'}")
        
        from order_executor import execute_order_swap as real_execute_swap
        
        # Определяем, какую мнемонику использовать
        test_mnemonic = None
        if use_real_mnemonic:
            test_mnemonic = ORDER_WALLET_MNEMONIC  # из тестового скрипта
            print(f"[ТЕСТ] Используем реальную мнемонику для тестирования отправки")
        else:
            print(f"[ТЕСТ] Используем режим подготовки (без отправки)")
        
        # Вызываем реальную функцию
        result = real_execute_swap(
            order=order,
            pool=pool,
            order_wallet_address=order_wallet_address,
            order_wallet_mnemonic=test_mnemonic,  # Используем выбранную мнемонику
            slippage=slippage
        )
        
        if result['success']:
            print(f"[ТЕСТ] ✅ Подготовка транзакции успешна")
            print(f"[ТЕСТ] Направление: {result['swap_details']['from_token']} -> {result['swap_details']['to_token']}")
            print(f"[ТЕСТ] Сумма: {result['swap_details']['from_amount']} -> {result['swap_details']['expected_output']:.6f}")
            print(f"[ТЕСТ] Транзакция отправлена: {result.get('transaction_sent', False)}")
            
            # Добавляем тестовую информацию
            result['message'] = 'Транзакция подготовлена (тестовый режим)'
            result['test_mode'] = True
            result['transaction_hash'] = f"test_tx_{int(datetime.now().timestamp())}"
        else:
            print(f"[ТЕСТ] ❌ Ошибка подготовки: {result.get('error', 'Unknown error')}")
        
        return result
    
    return mock_execute_swap

def test_real_transaction_send():
    """Тест реальной отправки транзакции (только если установлена мнемоника)"""
    print("\n" + "="*60)
    print("ТЕСТ 6: Реальная отправка транзакции")
    print("="*60)
    
    if not ORDER_WALLET_MNEMONIC:
        print("❌ Мнемоника не установлена, пропускаем тест реальной отправки")
        print("💡 Установите ORDER_WALLET_MNEMONIC в .env для тестирования отправки транзакций")
        return
    
    # Создаем небольшой тестовый ордер для минимальной суммы
    order_id = f"test_realsend_{int(datetime.now().timestamp())}"
    
    order = {
        'id': order_id,
        'type': 'long',
        'pair': 'TON-USDT',
        'amount': 0.01,  # Минимальная сумма для теста
        'entry_price': 2.0,
        'stop_loss': 1.9,
        'take_profit': 2.1,
        'user_wallet': "EQC7RQVpFx9h4FCL2Yif-rNie9Z-W4qBkWbnkl75SkqEmc3Y",
        'order_wallet': order_wallet_address,
        'status': 'opened',
        'created_at': datetime.now().isoformat(),
        'funded_at': datetime.now().isoformat(),
        'opened_at': datetime.now().isoformat(),
        'execution_price': 2.0,
        'price_at_creation': 1.99,
        'max_slippage': DEFAULT_SLIPPAGE
    }
    
    save_order(order)
    print(f"✅ Создан тестовый ордер для реальной отправки: 0.01 TON -> USDT")
    
    # Тестируем с реальной мнемоникой
    try:
        from order_executor import execute_order_swap
        import app
        
        # Получаем данные пула
        pool = pools.get('TON-USDT')
        if not pool:
            print("❌ Пул TON-USDT не найден в конфигурации")
            return
        
        print(f"\n🔄 Тестируем реальную отправку транзакции...")
        print(f"   Пул: {pool.get('dex', 'Unknown')}")
        print(f"   Адрес пула: {pool['address'][:20]}...")
        print(f"   Используется реальная мнемоника: ДА")
        
        # Вызываем функцию обмена с реальной мнемоникой
        result = execute_order_swap(
            order=order,
            pool=pool,
            order_wallet_address=order_wallet_address,
            order_wallet_mnemonic=ORDER_WALLET_MNEMONIC,  # Реальная мнемоника!
            slippage=DEFAULT_SLIPPAGE
        )
        
        if result['success']:
            print(f"✅ Подготовка обмена успешна!")
            print(f"   Направление: {result['swap_details']['from_token']} -> {result['swap_details']['to_token']}")
            print(f"   Сумма: {result['swap_details']['from_amount']} {result['swap_details']['from_token']}")
            print(f"   Ожидаемый выход: {result['swap_details']['expected_output']:.6f} {result['swap_details']['to_token']}")
            print(f"   Транзакция отправлена: {result.get('transaction_sent', False)}")
            print(f"   Сообщение: {result.get('message', 'N/A')}")
            
            if result.get('transaction_sent'):
                print(f"🎉 ТРАНЗАКЦИЯ УСПЕШНО ОТПРАВЛЕНА В БЛОКЧЕЙН!")
            else:
                print(f"⚠️ Транзакция подготовлена, но не отправлена")
                
        else:
            print(f"❌ Ошибка подготовки обмена: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        print(f"❌ Ошибка при тестировании отправки: {e}")
        import traceback
        traceback.print_exc()

def test_order_opening():
    """Тест открытия ордера (достижение entry_price)"""
    print("\n" + "="*60)
    print("ТЕСТ 1: Открытие ордера (достижение entry_price)")
    print("="*60)
    
    # Создаем LONG ордер с entry_price = 1.8, текущая цена = 1.79
    order_id = f"test_open_{int(datetime.now().timestamp())}"
    create_test_order(
        order_id=order_id,
        order_type='long',
        entry_price=1.8,
        stop_loss=1.74,
        take_profit=1.84,
        current_price=1.79,  # Цена ниже entry (Buy Stop)
        amount=1.0
    )
    
    # Мокаем get_current_price для возврата цены >= entry_price
    original_get_current_price = None
    original_execute_order_swap = None
    try:
        import app
        original_get_current_price = app.get_current_price
        original_execute_order_swap = app.execute_order_swap
        
        # Устанавливаем мок-цену 1.81 (выше entry_price)
        def mock_price(*args, **kwargs):
            return 1.81
        
        app.get_current_price = mock_price
        app.execute_order_swap = create_mock_execute_swap()
        
        # Запускаем проверку ордеров
        print(f"\n📊 Проверяем ордер {order_id}...")
        print(f"   Текущая цена (мок): 1.81")
        print(f"   Entry price: 1.80")
        print(f"   Ожидаем: ордер должен открыться")
        
        check_orders_execution()
        
        # Проверяем результат
        orders_data = load_orders()
        test_order = next((o for o in orders_data['orders'] if o['id'] == order_id), None)
        
        if test_order:
            if test_order['status'] == 'opened':
                print(f"✅ УСПЕХ: Ордер {order_id} открыт!")
                print(f"   Статус: {test_order['status']}")
                print(f"   Opened at: {test_order.get('opened_at', 'N/A')}")
                print(f"   Execution price: {test_order.get('execution_price', 'N/A')}")
            else:
                print(f"❌ ОШИБКА: Ордер не открыт, статус: {test_order['status']}")
        else:
            print(f"❌ ОШИБКА: Ордер {order_id} не найден")
    
    finally:
        # Восстанавливаем оригинальные функции
        if original_get_current_price:
            app.get_current_price = original_get_current_price
        if original_execute_order_swap:
            app.execute_order_swap = original_execute_order_swap


def test_take_profit_execution():
    """Тест исполнения по Take Profit"""
    print("\n" + "="*60)
    print("ТЕСТ 2: Исполнение по Take Profit")
    print("="*60)
    
    # Создаем открытый LONG ордер с TP = 1.84
    order_id = f"test_tp_{int(datetime.now().timestamp())}"
    
    order = {
        'id': order_id,
        'type': 'long',
        'pair': 'TON-USDT',
        'amount': 1.0,
        'entry_price': 1.80,
        'stop_loss': 1.74,
        'take_profit': 1.84,
        'user_wallet': "EQC7RQVpFx9h4FCL2Yif-rNie9Z-W4qBkWbnkl75SkqEmc3Y",
        'order_wallet': "UQD1V6ZNou__gvGZ9b-c69g9n1aXvSN4HJG1avp-AHDSRueL",
        'status': 'opened',  # Уже открыт
        'created_at': datetime.now().isoformat(),
        'funded_at': datetime.now().isoformat(),
        'opened_at': datetime.now().isoformat(),
        'execution_price': 1.80,
        'price_at_creation': 1.79,
        'max_slippage': DEFAULT_SLIPPAGE
    }
    
    save_order(order)
    print(f"✅ Создан открытый ордер {order_id}: LONG, entry=1.80, TP=1.84")
    
    # Мокаем get_current_price и execute_order_swap
    try:
        import app
        original_get_current_price = app.get_current_price
        original_execute_order_swap = app.execute_order_swap
        
        # Мок-цена выше TP
        def mock_price(*args, **kwargs):
            return 1.85  # Выше TP = 1.84
        
        app.get_current_price = mock_price
        app.execute_order_swap = create_mock_execute_swap()
        
        # Запускаем проверку
        print(f"\n📊 Проверяем ордер {order_id}...")
        print(f"   Текущая цена (мок): 1.85")
        print(f"   Entry price: 1.80")
        print(f"   Take Profit: 1.84")
        print(f"   Ожидаем: исполнение по TP")
        
        check_orders_execution()
        
        # Проверяем результат
        orders_data = load_orders()
        test_order = next((o for o in orders_data['orders'] if o['id'] == order_id), None)
        
        if test_order:
            if test_order['status'] == 'executed':
                print(f"✅ УСПЕХ: Ордер {order_id} исполнен по TP!")
                print(f"   Статус: {test_order['status']}")
                print(f"   Execution type: {test_order.get('execution_type', 'N/A')}")
                print(f"   PnL: {test_order.get('pnl', 0):.6f} USDT")
                print(f"   Executed at: {test_order.get('executed_at', 'N/A')}")
                
                # Проверяем PnL
                expected_pnl = (1.84 - 1.80) * 1.0  # (TP - entry) * amount
                actual_pnl = test_order.get('pnl', 0)
                if abs(actual_pnl - expected_pnl) < 0.01:
                    print(f"✅ PnL рассчитан правильно: {actual_pnl:.6f} (ожидалось {expected_pnl:.6f})")
                else:
                    print(f"⚠️  PnL не совпадает: {actual_pnl:.6f} (ожидалось {expected_pnl:.6f})")
                
                # Проверяем данные транзакции
                if test_order.get('swap_result'):
                    swap_result = test_order['swap_result']
                    print(f"   Результат обмена: {swap_result.get('message', 'N/A')}")
            else:
                print(f"❌ ОШИБКА: Ордер не исполнен, статус: {test_order['status']}")
        else:
            print(f"❌ ОШИБКА: Ордер {order_id} не найден")
    
    finally:
        # Восстанавливаем функции
        if original_get_current_price:
            app.get_current_price = original_get_current_price
        if original_execute_order_swap:
            app.execute_order_swap = original_execute_order_swap


def test_stop_loss_execution():
    """Тест исполнения по Stop Loss"""
    print("\n" + "="*60)
    print("ТЕСТ 3: Исполнение по Stop Loss")
    print("="*60)
    
    # Создаем открытый LONG ордер с SL = 1.74
    order_id = f"test_sl_{int(datetime.now().timestamp())}"
    
    order = {
        'id': order_id,
        'type': 'long',
        'pair': 'TON-USDT',
        'amount': 1.0,
        'entry_price': 1.80,
        'stop_loss': 1.74,
        'take_profit': 1.84,
        'user_wallet': "EQC7RQVpFx9h4FCL2Yif-rNie9Z-W4qBkWbnkl75SkqEmc3Y",
        'order_wallet': "UQD1V6ZNou__gvGZ9b-c69g9n1aXvSN4HJG1avp-AHDSRueL",
        'status': 'opened',
        'created_at': datetime.now().isoformat(),
        'funded_at': datetime.now().isoformat(),
        'opened_at': datetime.now().isoformat(),
        'execution_price': 1.80,
        'price_at_creation': 1.79,
        'max_slippage': DEFAULT_SLIPPAGE
    }
    
    save_order(order)
    print(f"✅ Создан открытый ордер {order_id}: LONG, entry=1.80, SL=1.74")
    
    # Мокаем функции
    try:
        import app
        original_get_current_price = app.get_current_price
        original_execute_order_swap = app.execute_order_swap
        
        # Мок-цена ниже SL
        def mock_price(*args, **kwargs):
            return 1.73  # Ниже SL = 1.74
        
        app.get_current_price = mock_price
        app.execute_order_swap = create_mock_execute_swap()
        
        # Запускаем проверку
        print(f"\n📊 Проверяем ордер {order_id}...")
        print(f"   Текущая цена (мок): 1.73")
        print(f"   Entry price: 1.80")
        print(f"   Stop Loss: 1.74")
        print(f"   Ожидаем: исполнение по SL")
        
        check_orders_execution()
        
        # Проверяем результат
        orders_data = load_orders()
        test_order = next((o for o in orders_data['orders'] if o['id'] == order_id), None)
        
        if test_order:
            if test_order['status'] == 'executed':
                print(f"✅ УСПЕХ: Ордер {order_id} исполнен по SL!")
                print(f"   Статус: {test_order['status']}")
                print(f"   Execution type: {test_order.get('execution_type', 'N/A')}")
                print(f"   PnL: {test_order.get('pnl', 0):.6f} USDT")
                print(f"   Executed at: {test_order.get('executed_at', 'N/A')}")
                
                # Проверяем PnL (для LONG: (SL - entry) * amount)
                expected_pnl = (1.74 - 1.80) * 1.0  # Отрицательный PnL
                actual_pnl = test_order.get('pnl', 0)
                if abs(actual_pnl - expected_pnl) < 0.01:
                    print(f"✅ PnL рассчитан правильно: {actual_pnl:.6f} (ожидалось {expected_pnl:.6f})")
                else:
                    print(f"⚠️  PnL не совпадает: {actual_pnl:.6f} (ожидалось {expected_pnl:.6f})")
            else:
                print(f"❌ ОШИБКА: Ордер не исполнен, статус: {test_order['status']}")
        else:
            print(f"❌ ОШИБКА: Ордер {order_id} не найден")
    
    finally:
        # Восстанавливаем функции
        if original_get_current_price:
            app.get_current_price = original_get_current_price
        if original_execute_order_swap:
            app.execute_order_swap = original_execute_order_swap


def test_short_order():
    """Тест SHORT ордера"""
    print("\n" + "="*60)
    print("ТЕСТ 4: SHORT ордер (Take Profit)")
    print("="*60)
    
    # Создаем открытый SHORT ордер
    order_id = f"test_short_{int(datetime.now().timestamp())}"
    
    order = {
        'id': order_id,
        'type': 'short',
        'pair': 'TON-USDT',
        'amount': 1.0,
        'entry_price': 1.80,
        'stop_loss': 1.86,  # Для SHORT SL выше entry
        'take_profit': 1.76,  # Для SHORT TP ниже entry
        'user_wallet': "EQC7RQVpFx9h4FCL2Yif-rNie9Z-W4qBkWbnkl75SkqEmc3Y",
        'order_wallet': "UQD1V6ZNou__gvGZ9b-c69g9n1aXvSN4HJG1avp-AHDSRueL",
        'status': 'opened',
        'created_at': datetime.now().isoformat(),
        'funded_at': datetime.now().isoformat(),
        'opened_at': datetime.now().isoformat(),
        'execution_price': 1.80,
        'price_at_creation': 1.81,
        'max_slippage': DEFAULT_SLIPPAGE
    }
    
    save_order(order)
    print(f"✅ Создан открытый SHORT ордер {order_id}: entry=1.80, TP=1.76")
    
    # Мокаем функции
    try:
        import app
        original_get_current_price = app.get_current_price
        original_execute_order_swap = app.execute_order_swap
        
        # Мок-цена ниже TP (для SHORT это хорошо)
        def mock_price(*args, **kwargs):
            return 1.75  # Ниже TP = 1.76
        
        app.get_current_price = mock_price
        app.execute_order_swap = create_mock_execute_swap()
        
        print(f"\n📊 Проверяем SHORT ордер {order_id}...")
        print(f"   Текущая цена (мок): 1.75")
        print(f"   Entry price: 1.80")
        print(f"   Take Profit: 1.76")
        print(f"   Ожидаем: исполнение по TP")
        
        check_orders_execution()
        
        # Проверяем результат
        orders_data = load_orders()
        test_order = next((o for o in orders_data['orders'] if o['id'] == order_id), None)
        
        if test_order:
            if test_order['status'] == 'executed':
                print(f"✅ УСПЕХ: SHORT ордер {order_id} исполнен по TP!")
                print(f"   Статус: {test_order['status']}")
                print(f"   Execution type: {test_order.get('execution_type', 'N/A')}")
                print(f"   PnL: {test_order.get('pnl', 0):.6f} USDT")
                
                # Проверяем PnL (для SHORT: (entry - TP) * amount)
                expected_pnl = (1.80 - 1.76) * 1.0  # Положительный PnL
                actual_pnl = test_order.get('pnl', 0)
                if abs(actual_pnl - expected_pnl) < 0.01:
                    print(f"✅ PnL рассчитан правильно: {actual_pnl:.6f} (ожидалось {expected_pnl:.6f})")
                else:
                    print(f"⚠️  PnL не совпадает: {actual_pnl:.6f} (ожидалось {expected_pnl:.6f})")
            else:
                print(f"❌ ОШИБКА: Ордер не исполнен, статус: {test_order['status']}")
        else:
            print(f"❌ ОШИБКА: Ордер {order_id} не найден")
    
    finally:
        if original_get_current_price:
            app.get_current_price = original_get_current_price
        if original_execute_order_swap:
            app.execute_order_swap = original_execute_order_swap

def test_real_swap_simulation():
    """Тест реального обмена 1 TON на USDT (симуляция)"""
    print("\n" + "="*60)
    print("ТЕСТ 5: Реальный обмен 1 TON на USDT (симуляция)")
    print("="*60)
    
    # Создаем тестовый ордер для реального обмена
    order_id = f"test_realswap_{int(datetime.now().timestamp())}"
    
    order = {
        'id': order_id,
        'type': 'long',
        'pair': 'TON-USDT',
        'amount': 1.0,  # 1 TON
        'entry_price': 2.0,
        'stop_loss': 1.9,
        'take_profit': 2.1,
        'user_wallet': "EQC7RQVpFx9h4FCL2Yif-rNie9Z-W4qBkWbnkl75SkqEmc3Y",
        'order_wallet': "UQD1V6ZNou__gvGZ9b-c69g9n1aXvSN4HJG1avp-AHDSRueL",
        'status': 'opened',
        'created_at': datetime.now().isoformat(),
        'funded_at': datetime.now().isoformat(),
        'opened_at': datetime.now().isoformat(),
        'execution_price': 2.0,
        'price_at_creation': 1.99,
        'max_slippage': DEFAULT_SLIPPAGE
    }
    
    save_order(order)
    print(f"✅ Создан тестовый ордер для обмена: 1 TON -> USDT")
    
    # Тестируем напрямую функцию execute_order_swap
    try:
        from order_executor import execute_order_swap
        import app
        
        # Получаем данные пула
        pool = pools.get('TON-USDT')
        if not pool:
            print("❌ Пул TON-USDT не найден в конфигурации")
            return
        
        print(f"\n🔄 Тестируем реальный обмен 1 TON на USDT...")
        print(f"   Пул: {pool.get('dex', 'Unknown')}")
        print(f"   Адрес пула: {pool['address'][:20]}...")
        
        # Вызываем функцию обмена
        result = execute_order_swap(
            order=order,
            pool=pool,
            order_wallet_address=order_wallet_address,
            order_wallet_mnemonic=None,  # Без реальной отправки
            slippage=DEFAULT_SLIPPAGE
        )
        
        if result['success']:
            print(f"✅ Подготовка обмена успешна!")
            print(f"   Направление: {result['swap_details']['from_token']} -> {result['swap_details']['to_token']}")
            print(f"   Сумма: {result['swap_details']['from_amount']} {result['swap_details']['from_token']}")
            print(f"   Ожидаемый выход: {result['swap_details']['expected_output']:.6f} {result['swap_details']['to_token']}")
            print(f"   Минимальный выход: {result['swap_details']['min_output']:.6f} {result['swap_details']['to_token']}")
            print(f"   Комиссия: {result['swap_details']['gas']:.6f} TON")
            print(f"   Адрес получателя: {result['transaction']['address']}")
            print(f"   Общая сумма: {int(result['transaction']['amount']) / 1e9:.6f} TON")
            
            # Проверяем, что транзакция подготовлена корректно
            if result['transaction']['payload']:
                print(f"   Payload подготовлен: {len(result['transaction']['payload'])} байт")
            else:
                print(f"   ⚠️ Payload не подготовлен")
                
        else:
            print(f"❌ Ошибка подготовки обмена: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        print(f"❌ Ошибка при тестировании обмена: {e}")
        import traceback
        traceback.print_exc()


def cleanup_test_orders():
    """Удаляет тестовые ордера из БД"""
    print("\n" + "="*60)
    print("Очистка тестовых ордеров...")
    print("="*60)
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM orders 
                    WHERE id LIKE 'test_%'
                """)
                deleted = cur.rowcount
                conn.commit()
                print(f"✅ Удалено тестовых ордеров: {deleted}")
    except Exception as e:
        print(f"❌ Ошибка при очистке: {e}")


def run_all_tests():
    """Запускает все тесты"""
    print("\n" + "="*60)
    print("ЗАПУСК ТЕСТОВ ФУНКЦИОНАЛА ОРДЕРОВ")
    print("="*60)
    
    try:
        # Тест 1: Открытие ордера
        test_order_opening()
        
        # Тест 2: Take Profit
        test_take_profit_execution()
        
        # Тест 3: Stop Loss
        test_stop_loss_execution()
        
        # Тест 4: SHORT ордер
        test_short_order()
        
        # Тест 5: Реальный обмен (подготовка)
        test_real_swap_simulation()
        
        # Тест 6: Реальная отправка (если есть мнемоника)
        test_real_transaction_send()
        
        print("\n" + "="*60)
        print("ВСЕ ТЕСТЫ ЗАВЕРШЕНЫ")
        print("="*60)
        
        # Опционально: очистка тестовых ордеров
        response = input("\nУдалить тестовые ордера из БД? (y/n): ")
        if response.lower() == 'y':
            cleanup_test_orders()
    
    except Exception as e:
        print(f"\n❌ ОШИБКА ПРИ ВЫПОЛНЕНИИ ТЕСТОВ: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_all_tests()

