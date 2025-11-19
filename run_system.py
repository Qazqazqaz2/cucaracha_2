import threading
import time
from snapshot_collector import SnapshotCollector
from order_manager import OrderManager
from app import app

def run_flask():
    app.run(debug=True, port=5000, use_reloader=False)

def run_snapshot_collector():
    collector = SnapshotCollector()
    collector.start_collection()

def run_order_manager():
    manager = OrderManager()
    manager.start_monitoring()

if __name__ == "__main__":
    print("Starting TON DEX System...")
    
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # Запускаем сборщик данных
    snapshot_thread = threading.Thread(target=run_snapshot_collector)
    snapshot_thread.daemon = True
    snapshot_thread.start()
    
    # Запускаем менеджер ордеров
    order_thread = threading.Thread(target=run_order_manager)
    order_thread.daemon = True
    order_thread.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping system...")