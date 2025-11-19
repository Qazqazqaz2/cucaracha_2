"""
Движок обработки ордеров - интеграция новой системы с существующим кодом
"""
import time
import threading
from decimal import Decimal
from datetime import datetime
from typing import Dict, List, Optional
import traceback

from order_system import (
    Order, OrderType, OrderStatus, PositionSide, TrailingConfig, TrailingType,
    OrderProcessor
)
from app import (
    get_db_connection, pools, get_current_price, load_orders, save_order
)


class OrderEngine:
    """Движок обработки ордеров с интеграцией в существующую систему"""
    
    def __init__(self):
        self.processor = OrderProcessor(self._get_price)
        self.running = False
        self.tick_interval = 1.0  # Интервал обработки тиков в секундах
    
    def _get_price(self, symbol: str) -> Decimal:
        """Получает текущую цену для символа"""
        if symbol not in pools:
            return Decimal("0")
        price = get_current_price(pools[symbol]['address'])
        return Decimal(str(price))
    
    def load_orders_from_db(self):
        """Загружает ордера из БД в процессор"""
        try:
            orders_data = load_orders()
            for order_dict in orders_data.get('orders', []):
                try:
                    # Конвертируем старый формат в новый
                    order = OrderEngine._convert_legacy_order(order_dict)
                    if order and order.status == OrderStatus.ACTIVE:
                        self.processor.add_order(order)
                except Exception as e:
                    print(f"[ENGINE] Error loading order {order_dict.get('id')}: {e}")
        except Exception as e:
            print(f"[ENGINE] Error loading orders: {e}")
    
    @staticmethod
    def _convert_legacy_order(order_dict: Dict) -> Optional[Order]:
        """Конвертирует старый формат ордера в новый"""
        try:
            # Определяем тип ордера
            order_type_str = order_dict.get('type', '').upper()
            if order_type_str in ['LONG', 'SHORT']:
                # Старый формат - это лимитный ордер на вход
                order_type = OrderType.LIMIT
                side = PositionSide.LONG if order_type_str == 'LONG' else PositionSide.SHORT
            else:
                order_type = OrderType(order_type_str) if order_type_str in [e.value for e in OrderType] else OrderType.LIMIT
                side = PositionSide.LONG  # По умолчанию
            
            # Определяем статус
            status_str = order_dict.get('status', 'PENDING').upper()
            status_map = {
                'UNFUNDED': OrderStatus.PENDING,
                'WAITING_ENTRY': OrderStatus.ACTIVE,
                'OPENED': OrderStatus.ACTIVE,
                'EXECUTED': OrderStatus.FILLED,
                'CANCELLED': OrderStatus.CANCELLED,
            }
            status = status_map.get(status_str, OrderStatus.PENDING)
            
            order = Order(
                id=order_dict['id'],
                symbol=order_dict.get('pair', ''),
                quantity=Decimal(str(order_dict.get('amount', 0))),
                type=order_type,
                status=status,
                side=side,
                limit_price=Decimal(str(order_dict['entry_price'])) if order_dict.get('entry_price') else None,
                stop_loss=Decimal(str(order_dict['stop_loss'])) if order_dict.get('stop_loss') else None,
                take_profit=Decimal(str(order_dict['take_profit'])) if order_dict.get('take_profit') else None,
                user_wallet=order_dict.get('user_wallet', ''),
                order_wallet=order_dict.get('order_wallet', ''),
                created_at=datetime.fromisoformat(order_dict['created_at']) if isinstance(order_dict.get('created_at'), str) else datetime.now(),
                execution_price=Decimal(str(order_dict['execution_price'])) if order_dict.get('execution_price') else None,
                execution_type=order_dict.get('execution_type'),
                pnl=Decimal(str(order_dict.get('pnl', 0))),
                entry_price=Decimal(str(order_dict['entry_price'])) if order_dict.get('entry_price') else None,
            )
            
            return order
        except Exception as e:
            print(f"[ENGINE] Error converting order: {e}")
            return None
    
    def save_order_to_db(self, order: Order):
        """Сохраняет ордер в БД"""
        try:
            order_dict = order.to_dict()
            # Адаптируем под существующую схему БД
            db_order = {
                'id': order.id,
                'type': order.side.value.lower(),  # Для совместимости
                'pair': order.symbol,
                'amount': float(order.quantity),
                'entry_price': float(order.limit_price or order.entry_price or 0),
                'stop_loss': float(order.stop_loss) if order.stop_loss else None,
                'take_profit': float(order.take_profit) if order.take_profit else None,
                'user_wallet': order.user_wallet,
                'order_wallet': order.order_wallet,
                'status': self._map_status_to_legacy(order.status),
                'created_at': order.created_at.isoformat(),
                'funded_at': order.filled_at.isoformat() if order.filled_at else None,
                'opened_at': order.filled_at.isoformat() if order.filled_at and order.status == OrderStatus.FILLED else None,
                'executed_at': order.filled_at.isoformat() if order.filled_at else None,
                'execution_price': float(order.execution_price) if order.execution_price else None,
                'execution_type': order.execution_type,
                'cancelled_at': order.cancelled_at.isoformat() if order.cancelled_at else None,
                'pnl': float(order.pnl),
                'price_at_creation': float(order.execution_price) if order.execution_price else None,
            }
            save_order(db_order)
        except Exception as e:
            print(f"[ENGINE] Error saving order: {e}")
            traceback.print_exc()
    
    def _map_status_to_legacy(self, status: OrderStatus) -> str:
        """Маппинг нового статуса в старый формат"""
        status_map = {
            OrderStatus.PENDING: 'unfunded',
            OrderStatus.ACTIVE: 'waiting_entry',
            OrderStatus.FILLED: 'executed',
            OrderStatus.CANCELLED: 'cancelled',
            OrderStatus.REJECTED: 'cancelled',
        }
        return status_map.get(status, 'pending')
    
    def process_all_symbols(self):
        """Обрабатывает тики для всех символов"""
        executed_orders = []
        
        for symbol in pools.keys():
            try:
                price = self._get_price(symbol)
                if price > 0:
                    orders = self.processor.process_tick(symbol, price)
                    executed_orders.extend(orders)
            except Exception as e:
                print(f"[ENGINE] Error processing {symbol}: {e}")
        
        # Сохраняем исполненные ордера
        for order in executed_orders:
            self.save_order_to_db(order)
            self.processor.remove_order(order.id)
        
        return executed_orders
    
    def start(self):
        """Запускает движок обработки ордеров"""
        if self.running:
            return
        
        self.running = True
        self.load_orders_from_db()
        
        def engine_loop():
            while self.running:
                try:
                    self.process_all_symbols()
                    time.sleep(self.tick_interval)
                except Exception as e:
                    print(f"[ENGINE] Error in engine loop: {e}")
                    traceback.print_exc()
                    time.sleep(5)
        
        engine_thread = threading.Thread(target=engine_loop)
        engine_thread.daemon = True
        engine_thread.start()
        print("[ENGINE] Order engine started")
    
    def stop(self):
        """Останавливает движок"""
        self.running = False
    
    def create_order(self, order_data: Dict) -> Order:
        """Создает новый ордер"""
        # Генерируем ID
        order_id = f"order_{int(time.time())}_{hash(str(order_data)) % 10000}"
        
        # Определяем тип и сторону
        order_type_str = order_data.get('order_type', 'LIMIT').upper()
        order_type = OrderType[order_type_str] if order_type_str in OrderType.__members__ else OrderType.LIMIT
        
        side_str = order_data.get('side', 'LONG').upper()
        side = PositionSide[side_str] if side_str in PositionSide.__members__ else PositionSide.LONG
        
        # Создаем ордер
        order = Order(
            id=order_id,
            symbol=order_data['symbol'],
            quantity=Decimal(str(order_data['quantity'])),
            type=order_type,
            status=OrderStatus.ACTIVE,
            side=side,
            limit_price=Decimal(str(order_data['limit_price'])) if order_data.get('limit_price') else None,
            stop_price=Decimal(str(order_data['stop_price'])) if order_data.get('stop_price') else None,
            take_profit=Decimal(str(order_data['take_profit'])) if order_data.get('take_profit') else None,
            stop_loss=Decimal(str(order_data['stop_loss'])) if order_data.get('stop_loss') else None,
            max_slippage=Decimal(str(order_data.get('max_slippage', 0.5))),
            user_wallet=order_data.get('user_wallet', ''),
            order_wallet=order_data.get('order_wallet', ''),
            entry_price=Decimal(str(order_data['entry_price'])) if order_data.get('entry_price') else None,
        )
        
        # Настраиваем трейлинг-стоп
        if order_data.get('trailing_type') and order_data.get('trailing_distance'):
            trailing_type = TrailingType[order_data['trailing_type'].upper()]
            trailing_distance = Decimal(str(order_data['trailing_distance']))
            order.trailing = TrailingConfig(
                type=trailing_type,
                distance=trailing_distance
            )
        
        # Настраиваем OCO
        if order_data.get('oco_group_id'):
            order.oco_group_id = order_data['oco_group_id']
            if order_data.get('oco_related_ids'):
                order.oco_related_ids = set(order_data['oco_related_ids'])
        
        # Добавляем в процессор
        self.processor.add_order(order)
        
        # Сохраняем в БД
        self.save_order_to_db(order)
        
        return order
    
    def create_oco_order(self, tp_order_data: Dict, sl_order_data: Dict) -> tuple:
        """Создает пару OCO ордеров (TP и SL)"""
        oco_group_id = f"oco_{int(time.time())}"
        
        # Создаем TP ордер
        tp_order_data['order_type'] = 'TAKE_PROFIT'
        tp_order_data['oco_group_id'] = oco_group_id
        tp_order = self.create_order(tp_order_data)
        
        # Создаем SL ордер
        sl_order_data['order_type'] = 'STOP_LOSS'
        sl_order_data['oco_group_id'] = oco_group_id
        sl_order = self.create_order(sl_order_data)
        
        # Связываем ордера
        tp_order.oco_related_ids.add(sl_order.id)
        sl_order.oco_related_ids.add(tp_order.id)
        
        # Обновляем в процессоре
        self.processor.add_order(tp_order)
        self.processor.add_order(sl_order)
        
        return tp_order, sl_order
    
    def get_slippage_stats(self) -> Dict:
        """Возвращает статистику проскальзывания"""
        return self.processor.get_slippage_stats()


# Глобальный экземпляр движка
_engine: Optional[OrderEngine] = None

def get_order_engine() -> OrderEngine:
    """Получает глобальный экземпляр движка"""
    global _engine
    if _engine is None:
        _engine = OrderEngine()
        _engine.start()
    return _engine

