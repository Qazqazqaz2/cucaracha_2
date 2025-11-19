import os
import time
import psycopg2
from dotenv import load_dotenv
from datetime import datetime
import asyncio
import threading
import traceback  # <-- ДОБАВЛЕНО
from app import pools, get_current_price, order_wallet_address, get_balance, load_orders, save_order  # <-- ДОБАВЛЕНО load_orders и save_order

load_dotenv()

PG_CONN = os.environ.get("PG_CONN", "dbname=lpm user=postgres password=762341 host=localhost port=5432")

class OrderManager:
    def __init__(self):
        self.conn = None
        self.running = False
    
    def connect_db(self):
        try:
            self.conn = psycopg2.connect(PG_CONN)
            print("[ORDER MANAGER] Connected to PostgreSQL")
            return True
        except Exception as e:
            print(f"[ORDER MANAGER] DB connection error: {e}")
            return False
    
    def create_orders_table(self):
        """Создание таблицы ордеров"""
        try:
            with self.conn.cursor() as cur:
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
                        executed_at TIMESTAMP,
                        execution_price NUMERIC(20,8),
                        execution_type VARCHAR(16),
                        cancelled_at TIMESTAMP,
                        pnl NUMERIC(20,8) DEFAULT 0
                    );
                    
                    CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status, pair);
                    CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_wallet, created_at);
                """)
                self.conn.commit()
                print("[ORDER MANAGER] Orders table created/verified")
        except Exception as e:
            print(f"[ORDER MANAGER] Table creation error: {e}")
    
    def check_orders_funding(self):
        """Проверка поступления средств для ордеров"""
        try:
            with self.conn.cursor() as cur:
                # Получаем unfunded ордера
                cur.execute("SELECT * FROM orders WHERE status = 'unfunded'")
                unfunded_orders = cur.fetchall()
                
                balance = get_balance(order_wallet_address)
                updated = False
                
                for order in unfunded_orders:
                    order_id, order_type, pair, amount, entry_price, stop_loss, take_profit, user_wallet, order_wallet, status, created_at, funded_at, executed_at, execution_price, execution_type, cancelled_at, pnl = order
                    
                    required_amount = amount + 0.1  # +0.1 TON для газа
                    
                    if balance >= required_amount:
                        # Обновляем статус ордера
                        cur.execute("""
                            UPDATE orders 
                            SET status = 'active', funded_at = NOW() 
                            WHERE id = %s AND status = 'unfunded'
                        """, (order_id,))
                        updated = True
                        print(f"[ORDER MANAGER] Order {order_id} funded and activated")
                
                if updated:
                    self.conn.commit()
                    
        except Exception as e:
            print(f"[ORDER MANAGER] Funding check error: {e}")
        
    def check_orders_execution(self):
        """Проверяет выполнение условий для ордеров с фиксированной ценой исполнения"""
        try:
            orders_data = load_orders()  # <-- ТЕПЕРЬ ФУНКЦИЯ ИМПОРТИРОВАНА
            active_orders = [o for o in orders_data['orders'] if o['status'] == 'active']
            
            if not active_orders:
                return
            
            # Получаем текущие цены для всех пар
            current_prices = {}
            for pool_name, pool in pools.items():
                current_prices[pool_name] = get_current_price(pool['address'])
            
            for order in active_orders:
                if order['status'] == 'pending':
                    should_fill = False
                    if order['type'] == 'long':
                        # Assuming buy stop if entry > current at creation, but since creation time current may change, perhaps store order subtype or just fill when crosses entry.
                        # Simple: fill if abs(current - entry) < threshold, but for demo:
                        if abs(current_price - entry_price) < 0.01:  # Small threshold
                            should_fill = True
                    # Similar for short
                    if should_fill:
                        order['status'] = 'active'
                        order['funded_at'] = datetime.now().isoformat()  # Or 'filled_at'
                        order['execution_price'] = current_price  # Actual fill
                        save_order(order)
                        print(f"[ORDER] Filled {order['id']} at {current_price}")
                        continue  # Don't check SL/TP yet
                pair = order['pair']
                if pair not in current_prices or current_prices[pair] == 0:
                    continue
                    
                current_price = current_prices[pair]
                entry_price = order['entry_price']
                stop_loss = order.get('stop_loss')
                take_profit = order.get('take_profit')
                
                print(f"[DEBUG] Checking order {order['id']}: current={current_price}, entry={entry_price}, SL={stop_loss}, TP={take_profit}")
                
                # Проверяем условия исполнения
                should_execute = False
                execution_type = ""
                execution_price = entry_price
                
                if order['type'] == 'long':
                    if stop_loss and current_price <= stop_loss:
                        should_execute = True
                        execution_type = "STOP_LOSS"
                        order['pnl'] = (stop_loss - entry_price) * order['amount']  # PnL в USDT
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
                    order['status'] = 'executed'
                    order['executed_at'] = datetime.now().isoformat()
                    order['execution_type'] = execution_type
                    order['execution_price'] = execution_price
                    save_order(order)  # <-- ТЕПЕРЬ ФУНКЦИЯ ИМПОРТИРОВАНА
                    print(f"[ORDER] Executed {order['id']} at fixed price {execution_price} (Market: {current_price}) - {execution_type}")
                
        except Exception as e:
            print(f"[ORDER CHECK] Error: {e}")
            traceback.print_exc()
    
    def get_order_stats(self, user_wallet=None):
        """Получение статистики по ордерам"""
        try:
            with self.conn.cursor() as cur:
                if user_wallet:
                    cur.execute("""
                        SELECT 
                            COUNT(*) as total_orders,
                            SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) as active_orders,
                            SUM(CASE WHEN status = 'executed' THEN 1 ELSE 0 END) as executed_orders,
                            SUM(CASE WHEN status = 'executed' THEN pnl ELSE 0 END) as total_pnl,
                            AVG(CASE WHEN status = 'executed' THEN pnl ELSE NULL END) as avg_pnl
                        FROM orders 
                        WHERE user_wallet = %s
                    """, (user_wallet,))
                else:
                    cur.execute("""
                        SELECT 
                            COUNT(*) as total_orders,
                            SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) as active_orders,
                            SUM(CASE WHEN status = 'executed' THEN 1 ELSE 0 END) as executed_orders,
                            SUM(CASE WHEN status = 'executed' THEN pnl ELSE 0 END) as total_pnl
                        FROM orders
                    """)
                
                return cur.fetchone()
        except Exception as e:
            print(f"[ORDER MANAGER] Stats error: {e}")
            return None
    
    def start_monitoring(self):
        """Запуск мониторинга ордеров"""
        if not self.connect_db():
            return
        
        self.create_orders_table()
        self.running = True
        
        print("[ORDER MANAGER] Starting order monitoring...")
        
        while self.running:
            try:
                self.check_orders_funding()
                self.check_orders_execution()
                time.sleep(5)  # Проверка каждые 5 секунд
                
            except Exception as e:
                print(f"[ORDER MANAGER] Monitoring error: {e}")
                traceback.print_exc()  # <-- Добавлен импорт
                time.sleep(10)
    
    def stop_monitoring(self):
        """Остановка мониторинга"""
        self.running = False
        if self.conn:
            self.conn.close()

def main():
    manager = OrderManager()
    try:
        manager.start_monitoring()
    except KeyboardInterrupt:
        print("\n[ORDER MANAGER] Stopping monitoring...")
        manager.stop_monitoring()

if __name__ == "__main__":
    main()