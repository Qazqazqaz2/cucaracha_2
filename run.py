# Запуск TON Trading Bot

from config import TELEGRAM_TOKEN, TRADING_CONFIG
from telegram_bot import TelegramTradingBot

def main():
    print("🐍 Запуск Python TON Trading Bot")
    print("=" * 50)
    
    # Показываем конфигурацию
    print(f"🤖 Telegram Bot: {TELEGRAM_TOKEN[:10]}...")
    print(f"👛 Кошелек: {TRADING_CONFIG['wallet_address'][:15]}...")
    print(f"🎮 Режим: {'Демо' if TRADING_CONFIG['demo_mode'] else 'Реальный'}")
    print(f"🪙 Токенов: {len(TRADING_CONFIG['tokens'])}")
    
    # Создаем и запускаем бота
    bot = TelegramTradingBot(TELEGRAM_TOKEN, TRADING_CONFIG)
    bot.run()

if __name__ == "__main__":
    main()