import asyncio
import asyncpg

# Database (тот же, что в indexator.py)
DB_DSN = "postgresql://postgres:762341@localhost:5432/cryptoindexator"

async def get_jetton_addresses_from_db() -> dict:
    """
    Получает адреса Jetton контрактов из базы данных
    """
    try:
        conn = await asyncpg.connect(DB_DSN)
        try:
            rows = await conn.fetch("SELECT address FROM jettons LIMIT 5")
            jettons = {}
            for i, row in enumerate(rows):
                # Используем индекс как символ для демонстрации
                symbol = f"JET{i+1}"
                jettons[symbol] = row["address"]
            return jettons
        finally:
            await conn.close()
    except Exception as e:
        print(f"Error fetching jetton addresses from DB: {e}")
        return {}

async def demonstrate_bot_functionality():
    print("Демонстрация работы бота:")
    print("=" * 50)
    
    # 1. Получаем адреса jetton контрактов из базы данных (как просили)
    print("1. Получение адресов Jetton контрактов из базы данных:")
    jetton_addresses = await get_jetton_addresses_from_db()
    
    if not jetton_addresses:
        print("   Ошибка: не удалось получить адреса jetton токенов из базы данных.")
        return
    
    for symbol, address in jetton_addresses.items():
        print(f"   {symbol}: {address}")
    
    print("\n2. Обработка через TON API:")
    print("   В реальной реализации здесь происходит вызов TON API")
    print("   для получения метаданных и цен токенов.")
    
    print("\n3. Вывод информации пользователю:")
    result_lines = []
    for symbol, jetton_address in jetton_addresses.items():
        # В реальной реализации здесь будут реальные данные из TON API
        line = f"{symbol} / TON: 0.000000 TON\nName: Unknown Token\nDecimals: 9\nAddress: {jetton_address}"
        result_lines.append(line)
    
    text = "\n\n".join(result_lines)
    print(f"   Информация о Jetton токенах из БД:\n\n{text}")

if __name__ == "__main__":
    asyncio.run(demonstrate_bot_functionality())