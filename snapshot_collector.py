import os
import time
import psycopg2
from dotenv import load_dotenv
from datetime import datetime
import asyncio
import threading

load_dotenv()

# Конфигурация БД
PG_CONN = os.environ.get("PG_CONN", "dbname=lpm user=postgres password=762341 host=localhost port=5432")

# Импортируем функции из основного приложения
import sys
sys.path.append('.')

from app import pools, get_pool_reserves, get_current_price, SERVICE_FEE_RATE, get_expected_output

class SnapshotCollector:
    def __init__(self):
        self.conn = None
        self.running = False
        
    def connect_db(self):
        """Подключение к PostgreSQL"""
        try:
            self.conn = psycopg2.connect(PG_CONN)
            print("[SNAPSHOT] Connected to PostgreSQL")
            return True
        except Exception as e:
            print(f"[SNAPSHOT] DB connection error: {e}")
            return False
    
    def create_tables(self):
        """Создание таблиц если не существуют"""
        try:
            with self.conn.cursor() as cur:
                # Таблица снапшотов пулов
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS pool_snapshots (
                        id SERIAL PRIMARY KEY,
                        pool_name VARCHAR(32) NOT NULL,
                        pool_address VARCHAR(80) NOT NULL,
                        reserve_from NUMERIC(32,0) NOT NULL,
                        reserve_to NUMERIC(32,0) NOT NULL,
                        price NUMERIC(40,12) NOT NULL,
                        commission NUMERIC(20,10),
                        volume_24h NUMERIC(32,0) DEFAULT 0,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    );
                    
                    CREATE INDEX IF NOT EXISTS idx_pool_snapshots_pool_name ON pool_snapshots(pool_name);
                    CREATE INDEX IF NOT EXISTS idx_pool_snapshots_created_at ON pool_snapshots(created_at);
                    
                    -- Таблица для агрегированных данных (каждый час)
                    CREATE TABLE IF NOT EXISTS pool_aggregated (
                        id SERIAL PRIMARY KEY,
                        pool_name VARCHAR(32) NOT NULL,
                        date_hour TIMESTAMP NOT NULL,
                        open_price NUMERIC(40,12) NOT NULL,
                        close_price NUMERIC(40,12) NOT NULL,
                        high_price NUMERIC(40,12) NOT NULL,
                        low_price NUMERIC(40,12) NOT NULL,
                        volume NUMERIC(32,0) DEFAULT 0,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    );
                    
                    CREATE INDEX IF NOT EXISTS idx_pool_aggregated_pool_name ON pool_aggregated(pool_name, date_hour);
                """)
                self.conn.commit()
                print("[SNAPSHOT] Tables created/verified")
        except Exception as e:
            print(f"[SNAPSHOT] Table creation error: {e}")
    
    def save_snapshot(self, pool_name, pool_data):
        """Сохраняет снапшот пула в БД"""
        try:
            reserve_from, reserve_to = get_pool_reserves(pool_data['address'])
            price = get_current_price(pool_data['address'])
            
            # Расчет комиссий (сервисная + пула)
            commission = SERVICE_FEE_RATE + 0.003  # 0.25% + 0.3%
            
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO pool_snapshots (pool_name, pool_address, reserve_from, reserve_to, price, commission)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (pool_name, pool_data['address'], reserve_from, reserve_to, price, commission))
            
            self.conn.commit()
            
            print(f"[SNAPSHOT] Saved {pool_name}: price={price:.6f}, reserves=({reserve_from}, {reserve_to})")
            return True
            
        except Exception as e:
            print(f"[SNAPSHOT] Error saving {pool_name}: {e}")
            return False
    
    def calculate_24h_volume(self, pool_name):
        """Расчет объема за 24 часа (упрощенный)"""
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT SUM(reserve_from) as volume 
                    FROM pool_snapshots 
                    WHERE pool_name = %s AND created_at >= NOW() - INTERVAL '24 hours'
                """, (pool_name,))
                result = cur.fetchone()
                return result[0] if result[0] else 0
        except Exception as e:
            print(f"[SNAPSHOT] Volume calculation error: {e}")
            return 0
    
    def aggregate_hourly_data(self):
        """Агрегация данных по часам"""
        try:
            with self.conn.cursor() as cur:
                # Для каждого пула агрегируем данные за последний завершенный час
                cur.execute("""
                    INSERT INTO pool_aggregated (pool_name, date_hour, open_price, close_price, high_price, low_price, volume)
                    SELECT 
                        pool_name,
                        DATE_TRUNC('hour', created_at) as date_hour,
                        FIRST_VALUE(price) OVER (PARTITION BY pool_name, DATE_TRUNC('hour', created_at) ORDER BY created_at) as open_price,
                        LAST_VALUE(price) OVER (PARTITION BY pool_name, DATE_TRUNC('hour', created_at) ORDER BY created_at) as close_price,
                        MAX(price) as high_price,
                        MIN(price) as low_price,
                        SUM(reserve_from) as volume
                    FROM pool_snapshots 
                    WHERE created_at >= DATE_TRUNC('hour', NOW() - INTERVAL '1 hour')
                    AND created_at < DATE_TRUNC('hour', NOW())
                    GROUP BY pool_name, DATE_TRUNC('hour', created_at)
                    ON CONFLICT (pool_name, date_hour) DO UPDATE SET
                        close_price = EXCLUDED.close_price,
                        high_price = EXCLUDED.high_price,
                        low_price = EXCLUDED.low_price,
                        volume = EXCLUDED.volume
                """)
                self.conn.commit()
                print("[SNAPSHOT] Hourly aggregation completed")
        except Exception as e:
            print(f"[SNAPSHOT] Aggregation error: {e}")
    
    def start_collection(self):
        """Запуск сбора данных"""
        if not self.connect_db():
            return
        
        self.create_tables()
        self.running = True
        
        last_aggregation = time.time()
        
        print("[SNAPSHOT] Starting data collection...")
        
        while self.running:
            try:
                # Собираем данные для каждого пула
                for pool_name, pool_data in pools.items():
                    self.save_snapshot(pool_name, pool_data)
                
                # Агрегируем данные каждый час
                if time.time() - last_aggregation >= 3600:  # Каждый час
                    self.aggregate_hourly_data()
                    last_aggregation = time.time()
                
                time.sleep(1)  # Сбор каждую секунду
                
            except Exception as e:
                print(f"[SNAPSHOT] Collection error: {e}")
                time.sleep(5)
    
    def stop_collection(self):
        """Остановка сбора данных"""
        self.running = False
        if self.conn:
            self.conn.close()

def main():
    collector = SnapshotCollector()
    try:
        collector.start_collection()
    except KeyboardInterrupt:
        print("\n[SNAPSHOT] Stopping collection...")
        collector.stop_collection()

if __name__ == "__main__":
    main()