"""
Комплексная система управления ордерами для криптовалютной биржи
Включает: лимитные, рыночные, стоп-ордера, трейлинг-стопы, OCO ордера
"""
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Set
from datetime import datetime
from decimal import Decimal


class OrderType(Enum):
    """Типы ордеров"""
    LIMIT = "LIMIT"                    # Лимитный ордер
    MARKET = "MARKET"                  # Рыночный ордер
    STOP_LOSS = "STOP_LOSS"            # Стоп-лосс
    TAKE_PROFIT = "TAKE_PROFIT"        # Тейк-профит
    STOP_ENTRY = "STOP_ENTRY"          # Стоп-ордер на вход
    OCO = "OCO"                        # OCO ордер (связка)


class OrderStatus(Enum):
    """Статусы ордеров"""
    PENDING = "PENDING"                # Ожидает активации
    ACTIVE = "ACTIVE"                  # Активен, ожидает исполнения
    PARTIALLY_FILLED = "PARTIALLY_FILLED"  # Частично исполнен
    FILLED = "FILLED"                  # Полностью исполнен
    CANCELLED = "CANCELLED"            # Отменен
    REJECTED = "REJECTED"              # Отклонен
    EXPIRED = "EXPIRED"                # Истек


class TrailingType(Enum):
    """Тип трейлинг-стопа"""
    FIXED = "FIXED"                    # Фиксированное расстояние в пунктах
    PERCENTAGE = "PERCENTAGE"          # Процентное расстояние


class PositionSide(Enum):
    """Сторона позиции"""
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass
class TrailingConfig:
    """Конфигурация трейлинг-стопа"""
    type: TrailingType
    distance: Decimal                  # Дистанция в пунктах или процентах
    current_stop: Optional[Decimal] = None  # Текущее значение стопа
    highest_price: Optional[Decimal] = None  # Максимальная цена (для лонга)
    lowest_price: Optional[Decimal] = None   # Минимальная цена (для шорта)
    
    def update_for_long(self, current_price: Decimal) -> Optional[Decimal]:
        """Обновляет трейлинг-стоп для длинной позиции"""
        if self.highest_price is None or current_price > self.highest_price:
            self.highest_price = current_price
        
        if self.highest_price is None:
            return None
        
        if self.type == TrailingType.FIXED:
            new_stop = self.highest_price - self.distance
        else:  # PERCENTAGE
            new_stop = self.highest_price * (1 - self.distance / 100)
        
        if self.current_stop is None or new_stop > self.current_stop:
            self.current_stop = new_stop
        
        return self.current_stop
    
    def update_for_short(self, current_price: Decimal) -> Optional[Decimal]:
        """Обновляет трейлинг-стоп для короткой позиции"""
        if self.lowest_price is None or current_price < self.lowest_price:
            self.lowest_price = current_price
        
        if self.lowest_price is None:
            return None
        
        if self.type == TrailingType.FIXED:
            new_stop = self.lowest_price + self.distance
        else:  # PERCENTAGE
            new_stop = self.lowest_price * (1 + self.distance / 100)
        
        if self.current_stop is None or new_stop < self.current_stop:
            self.current_stop = new_stop
        
        return self.current_stop


@dataclass
class Order:
    """Базовый класс ордера"""
    id: str
    symbol: str                        # Пара (например, "TON-USDT")
    quantity: Decimal                  # Количество
    type: OrderType
    status: OrderStatus = OrderStatus.PENDING
    side: PositionSide                  # LONG или SHORT
    
    # Цены
    limit_price: Optional[Decimal] = None      # Для лимитных ордеров
    stop_price: Optional[Decimal] = None       # Для стоп-ордеров
    take_profit: Optional[Decimal] = None      # Тейк-профит
    stop_loss: Optional[Decimal] = None        # Стоп-лосс
    
    # Трейлинг
    trailing: Optional[TrailingConfig] = None
    
    # Проскальзывание
    max_slippage: Decimal = Decimal("0.5")     # Максимальное проскальзывание в %
    
    # Метаданные
    user_wallet: str = ""
    order_wallet: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    filled_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    
    # Исполнение
    execution_price: Optional[Decimal] = None
    execution_type: Optional[str] = None
    filled_quantity: Decimal = Decimal("0")
    pnl: Decimal = Decimal("0")
    
    # OCO связка
    oco_group_id: Optional[str] = None         # ID группы OCO ордеров
    oco_related_ids: Set[str] = field(default_factory=set)  # Связанные ордера
    
    # Для стоп-ордеров на вход
    entry_price: Optional[Decimal] = None      # Цена входа для позиции
    
    def to_dict(self) -> Dict:
        """Конвертирует ордер в словарь для сохранения в БД"""
        return {
            'id': self.id,
            'symbol': self.symbol,
            'quantity': float(self.quantity),
            'type': self.type.value,
            'status': self.status.value,
            'side': self.side.value,
            'limit_price': float(self.limit_price) if self.limit_price else None,
            'stop_price': float(self.stop_price) if self.stop_price else None,
            'take_profit': float(self.take_profit) if self.take_profit else None,
            'stop_loss': float(self.stop_loss) if self.stop_loss else None,
            'max_slippage': float(self.max_slippage),
            'user_wallet': self.user_wallet,
            'order_wallet': self.order_wallet,
            'created_at': self.created_at.isoformat(),
            'filled_at': self.filled_at.isoformat() if self.filled_at else None,
            'cancelled_at': self.cancelled_at.isoformat() if self.cancelled_at else None,
            'execution_price': float(self.execution_price) if self.execution_price else None,
            'execution_type': self.execution_type,
            'filled_quantity': float(self.filled_quantity),
            'pnl': float(self.pnl),
            'oco_group_id': self.oco_group_id,
            'oco_related_ids': list(self.oco_related_ids),
            'entry_price': float(self.entry_price) if self.entry_price else None,
            'trailing_type': self.trailing.type.value if self.trailing else None,
            'trailing_distance': float(self.trailing.distance) if self.trailing else None,
            'trailing_current_stop': float(self.trailing.current_stop) if self.trailing and self.trailing.current_stop else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Order':
        """Создает ордер из словаря (из БД)"""
        trailing = None
        if data.get('trailing_type') and data.get('trailing_distance'):
            trailing = TrailingConfig(
                type=TrailingType(data['trailing_type']),
                distance=Decimal(str(data['trailing_distance'])),
                current_stop=Decimal(str(data['trailing_current_stop'])) if data.get('trailing_current_stop') else None
            )
        
        order = cls(
            id=data['id'],
            symbol=data['symbol'],
            quantity=Decimal(str(data['quantity'])),
            type=OrderType(data['type']),
            status=OrderStatus(data['status']),
            side=PositionSide(data['side']),
            limit_price=Decimal(str(data['limit_price'])) if data.get('limit_price') else None,
            stop_price=Decimal(str(data['stop_price'])) if data.get('stop_price') else None,
            take_profit=Decimal(str(data['take_profit'])) if data.get('take_profit') else None,
            stop_loss=Decimal(str(data['stop_loss'])) if data.get('stop_loss') else None,
            trailing=trailing,
            max_slippage=Decimal(str(data.get('max_slippage', 0.5))),
            user_wallet=data.get('user_wallet', ''),
            order_wallet=data.get('order_wallet', ''),
            created_at=datetime.fromisoformat(data['created_at']) if isinstance(data.get('created_at'), str) else data.get('created_at', datetime.now()),
            filled_at=datetime.fromisoformat(data['filled_at']) if isinstance(data.get('filled_at'), str) and data['filled_at'] else None,
            cancelled_at=datetime.fromisoformat(data['cancelled_at']) if isinstance(data.get('cancelled_at'), str) and data['cancelled_at'] else None,
            execution_price=Decimal(str(data['execution_price'])) if data.get('execution_price') else None,
            execution_type=data.get('execution_type'),
            filled_quantity=Decimal(str(data.get('filled_quantity', 0))),
            pnl=Decimal(str(data.get('pnl', 0))),
            oco_group_id=data.get('oco_group_id'),
            oco_related_ids=set(data.get('oco_related_ids', [])),
            entry_price=Decimal(str(data['entry_price'])) if data.get('entry_price') else None,
        )
        return order


class OrderProcessor:
    """Процессор обработки ордеров с приоритетами"""
    
    def __init__(self, price_feed_callback):
        """
        Args:
            price_feed_callback: Функция получения текущей цены (symbol -> Decimal)
        """
        self.price_feed = price_feed_callback
        self.orders: Dict[str, Order] = {}
        self.oco_groups: Dict[str, Set[str]] = {}  # group_id -> set of order_ids
        self.slippage_stats: List[Dict] = []  # Статистика проскальзывания
    
    def add_order(self, order: Order):
        """Добавляет ордер в систему"""
        self.orders[order.id] = order
        
        # Регистрируем OCO группу
        if order.oco_group_id:
            if order.oco_group_id not in self.oco_groups:
                self.oco_groups[order.oco_group_id] = set()
            self.oco_groups[order.oco_group_id].add(order.id)
            
            # Связываем ордера в группе
            for related_id in order.oco_related_ids:
                if related_id in self.orders:
                    self.orders[related_id].oco_related_ids.add(order.id)
                    order.oco_related_ids.add(related_id)
    
    def remove_order(self, order_id: str):
        """Удаляет ордер из системы"""
        if order_id in self.orders:
            order = self.orders[order_id]
            
            # Удаляем из OCO группы
            if order.oco_group_id and order.oco_group_id in self.oco_groups:
                self.oco_groups[order.oco_group_id].discard(order_id)
                if not self.oco_groups[order.oco_group_id]:
                    del self.oco_groups[order.oco_group_id]
            
            del self.orders[order_id]
    
    def process_tick(self, symbol: str, price: Decimal) -> List[Order]:
        """
        Обрабатывает тик цены для символа
        Возвращает список исполненных ордеров
        
        Приоритет обработки:
        1. OCO ордера (проверка отмены)
        2. Трейлинг-стопы (обновление)
        3. Стоп-ордера (активация)
        4. Лимитные ордера
        5. Рыночные ордера
        """
        executed_orders = []
        
        # Получаем все активные ордера для символа
        active_orders = [
            o for o in self.orders.values()
            if o.symbol == symbol and o.status == OrderStatus.ACTIVE
        ]
        
        if not active_orders:
            return executed_orders
        
        # 1. Обработка OCO ордеров
        oco_orders = [o for o in active_orders if o.oco_group_id]
        for order in oco_orders:
            if self._check_oco_execution(order, price):
                executed_orders.append(order)
                # Отменяем связанные ордера
                self._cancel_oco_related(order)
        
        # 2. Обновление трейлинг-стопов
        trailing_orders = [o for o in active_orders if o.trailing and o.status == OrderStatus.ACTIVE]
        for order in trailing_orders:
            self._update_trailing_stop(order, price)
        
        # 3. Активация стоп-ордеров
        stop_orders = [
            o for o in active_orders
            if o.type in (OrderType.STOP_LOSS, OrderType.TAKE_PROFIT, OrderType.STOP_ENTRY)
            and o.status == OrderStatus.ACTIVE
        ]
        for order in stop_orders:
            if self._check_stop_activation(order, price):
                # Активируем стоп-ордер (превращаем в рыночный или лимитный)
                if self._execute_stop_order(order, price):
                    executed_orders.append(order)
        
        # 4. Исполнение лимитных ордеров
        limit_orders = [
            o for o in active_orders
            if o.type == OrderType.LIMIT and o.status == OrderStatus.ACTIVE
        ]
        for order in limit_orders:
            if self._check_limit_execution(order, price):
                if self._execute_limit_order(order, price):
                    executed_orders.append(order)
        
        # 5. Исполнение рыночных ордеров
        market_orders = [
            o for o in active_orders
            if o.type == OrderType.MARKET and o.status == OrderStatus.ACTIVE
        ]
        for order in market_orders:
            if self._execute_market_order(order, price):
                executed_orders.append(order)
        
        return executed_orders
    
    def _check_oco_execution(self, order: Order, price: Decimal) -> bool:
        """Проверяет, должен ли OCO ордер исполниться"""
        if order.type == OrderType.TAKE_PROFIT:
            if order.side == PositionSide.LONG:
                return price >= order.take_profit
            else:
                return price <= order.take_profit
        elif order.type == OrderType.STOP_LOSS:
            if order.side == PositionSide.LONG:
                return price <= order.stop_loss
            else:
                return price >= order.stop_loss
        return False
    
    def _cancel_oco_related(self, executed_order: Order):
        """Отменяет связанные OCO ордера"""
        for related_id in executed_order.oco_related_ids:
            if related_id in self.orders:
                related = self.orders[related_id]
                related.status = OrderStatus.CANCELLED
                related.cancelled_at = datetime.now()
    
    def _update_trailing_stop(self, order: Order, price: Decimal):
        """Обновляет трейлинг-стоп"""
        if not order.trailing:
            return
        
        if order.side == PositionSide.LONG:
            new_stop = order.trailing.update_for_long(price)
        else:
            new_stop = order.trailing.update_for_short(price)
        
        if new_stop and order.stop_loss:
            # Обновляем stop_loss если трейлинг-стоп выше (для лонга) или ниже (для шорта)
            if order.side == PositionSide.LONG:
                if new_stop > order.stop_loss:
                    order.stop_loss = new_stop
            else:
                if new_stop < order.stop_loss:
                    order.stop_loss = new_stop
    
    def _check_stop_activation(self, order: Order, price: Decimal) -> bool:
        """Проверяет, достигнута ли цена активации стоп-ордера"""
        if not order.stop_price:
            return False
        
        if order.type == OrderType.STOP_LOSS:
            if order.side == PositionSide.LONG:
                return price <= order.stop_price
            else:
                return price >= order.stop_price
        elif order.type == OrderType.TAKE_PROFIT:
            if order.side == PositionSide.LONG:
                return price >= order.stop_price
            else:
                return price <= order.stop_price
        elif order.type == OrderType.STOP_ENTRY:
            if order.side == PositionSide.LONG:
                return price >= order.stop_price
            else:
                return price <= order.stop_price
        
        return False
    
    def _execute_stop_order(self, order: Order, price: Decimal) -> bool:
        """Исполняет стоп-ордер (гарантированное исполнение, даже с проскальзыванием)"""
        # Стоп-ордера исполняются по рыночной цене с возможным проскальзыванием
        execution_price = price
        
        # Для стоп-лосса гарантируем исполнение
        if order.type == OrderType.STOP_LOSS:
            if order.side == PositionSide.LONG:
                # Для лонга стоп-лосс исполняется по цене не выше stop_price
                execution_price = min(price, order.stop_price)
            else:
                # Для шорта стоп-лосс исполняется по цене не ниже stop_price
                execution_price = max(price, order.stop_price)
        
        order.status = OrderStatus.FILLED
        order.filled_at = datetime.now()
        order.execution_price = execution_price
        order.execution_type = order.type.value
        order.filled_quantity = order.quantity
        
        # Расчет PnL
        if order.entry_price:
            if order.side == PositionSide.LONG:
                order.pnl = (execution_price - order.entry_price) * order.quantity
            else:
                order.pnl = (order.entry_price - execution_price) * order.quantity
        
        return True
    
    def _check_limit_execution(self, order: Order, price: Decimal) -> bool:
        """Проверяет, может ли лимитный ордер исполниться"""
        if not order.limit_price:
            return False
        
        if order.side == PositionSide.LONG:
            # Лонг: покупаем по цене не выше limit_price
            return price <= order.limit_price
        else:
            # Шорт: продаем по цене не ниже limit_price
            return price >= order.limit_price
    
    def _execute_limit_order(self, order: Order, price: Decimal) -> bool:
        """Исполняет лимитный ордер"""
        execution_price = order.limit_price
        
        order.status = OrderStatus.FILLED
        order.filled_at = datetime.now()
        order.execution_price = execution_price
        order.execution_type = "LIMIT"
        order.filled_quantity = order.quantity
        
        return True
    
    def _execute_market_order(self, order: Order, price: Decimal) -> bool:
        """Исполняет рыночный ордер с проверкой проскальзывания"""
        # Получаем ожидаемую цену (можно использовать orderbook или текущую цену)
        expected_price = price
        execution_price = price
        
        # Проверяем проскальзывание
        if order.limit_price:  # Если указана максимальная цена для рыночного ордера
            if order.side == PositionSide.LONG:
                if execution_price > order.limit_price:
                    slippage = ((execution_price - order.limit_price) / order.limit_price) * 100
                    if slippage > order.max_slippage:
                        # Отменяем ордер из-за превышения проскальзывания
                        order.status = OrderStatus.REJECTED
                        order.cancelled_at = datetime.now()
                        return False
            else:
                if execution_price < order.limit_price:
                    slippage = ((order.limit_price - execution_price) / order.limit_price) * 100
                    if slippage > order.max_slippage:
                        order.status = OrderStatus.REJECTED
                        order.cancelled_at = datetime.now()
                        return False
        
        # Логируем проскальзывание
        if expected_price != execution_price:
            slippage_pct = abs((execution_price - expected_price) / expected_price) * 100
            self.slippage_stats.append({
                'order_id': order.id,
                'expected_price': float(expected_price),
                'execution_price': float(execution_price),
                'slippage_pct': float(slippage_pct),
                'timestamp': datetime.now().isoformat()
            })
        
        order.status = OrderStatus.FILLED
        order.filled_at = datetime.now()
        order.execution_price = execution_price
        order.execution_type = "MARKET"
        order.filled_quantity = order.quantity
        
        return True
    
    def get_slippage_stats(self) -> Dict:
        """Возвращает статистику проскальзывания"""
        if not self.slippage_stats:
            return {'total_orders': 0, 'avg_slippage': 0, 'max_slippage': 0}
        
        slippages = [s['slippage_pct'] for s in self.slippage_stats]
        return {
            'total_orders': len(self.slippage_stats),
            'avg_slippage': sum(slippages) / len(slippages),
            'max_slippage': max(slippages),
            'min_slippage': min(slippages),
            'recent': self.slippage_stats[-10:]  # Последние 10
        }

