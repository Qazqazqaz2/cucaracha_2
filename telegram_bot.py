# Telegram Bot для TON Trading Engine

import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from trading_engine import TonTradingEngine, TradeResult

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TelegramTradingBot:
    def __init__(self, telegram_token: str, trading_config: dict):
        self.telegram_token = telegram_token
        self.trading_config = trading_config
        self.trading_engine = None
        self.user_sessions = {}  # Храним сессии пользователей
        
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        user = update.effective_user
        welcome_text = f"""
🐍 <b>TON Trading Bot (Python)</b>

Привет, {user.first_name}! 👋

🔥 <b>Возможности:</b>
• 💰 Покупка/продажа токенов
• 📊 Мониторинг портфеля  
• 🎯 Лучшие цены с DEX
• ⚡ Быстрые транзакции

<b>💡 Команды:</b>
/portfolio - портфель
/buy - купить токен
/sell - продать токен
/balance - баланс
/help - помощь
        """
        
        keyboard = [
            [InlineKeyboardButton("💼 Портфель", callback_data="portfolio")],
            [InlineKeyboardButton("💰 Купить", callback_data="buy_menu"),
             InlineKeyboardButton("💸 Продать", callback_data="sell_menu")],
            [InlineKeyboardButton("💳 Баланс", callback_data="balance"),
             InlineKeyboardButton("❓ Помощь", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_text, parse_mode='HTML', reply_markup=reply_markup)

    async def portfolio_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /portfolio"""
        await self.show_portfolio(update, context)

    async def show_portfolio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает портфель пользователя"""
        try:
            # Отправляем сообщение о загрузке
            loading_msg = await update.effective_message.reply_text("⏳ Загружаю портфель...")
            
            async with TonTradingEngine(self.trading_config) as engine:
                portfolio = await engine.get_portfolio()
            
            # Формируем текст портфеля
            portfolio_text = "💼 <b>Ваш портфель</b>\n\n"
            portfolio_text += f"💰 <b>Общая стоимость:</b> {portfolio['total_value_ton']:.4f} TON\n\n"
            
            # TON баланс
            ton_balance = portfolio["balances"].get("TON", 0)
            portfolio_text += f"💎 TON: {ton_balance:.4f}\n"
            
            # Токены
            if portfolio["tokens"]:
                portfolio_text += "\n🪙 <b>Токены:</b>\n"
                for token in portfolio["tokens"]:
                    percentage = (token["value_ton"] / portfolio["total_value_ton"] * 100) if portfolio["total_value_ton"] > 0 else 0
                    portfolio_text += f"• {token['symbol']}: {token['balance']:.2f} (≈{token['value_ton']:.4f} TON, {percentage:.1f}%)\n"
            
            # Кнопки управления
            keyboard = [
                [InlineKeyboardButton("🔄 Обновить", callback_data="portfolio")],
                [InlineKeyboardButton("💰 Купить", callback_data="buy_menu"),
                 InlineKeyboardButton("💸 Продать", callback_data="sell_menu")],
                [InlineKeyboardButton("📊 Детали", callback_data="portfolio_details")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await loading_msg.edit_text(portfolio_text, parse_mode='HTML', reply_markup=reply_markup)
            
        except Exception as error:
            await update.effective_message.reply_text(f"❌ Ошибка получения портфеля: {error}")

    async def buy_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /buy [токен] [сумма]"""
        args = context.args
        
        if len(args) >= 2:
            token_symbol = args[0].upper()
            try:
                amount = float(args[1])
                await self.execute_buy(update, token_symbol, amount)
            except ValueError:
                await update.message.reply_text("❌ Неправильная сумма. Используйте: /buy USDT 1.5")
        else:
            await self.show_buy_menu(update, context)

    async def show_buy_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает меню покупки"""
        buy_text = """
💰 <b>Покупка токенов</b>

🔸 <b>Быстрая покупка:</b>
Выберите токен ниже

🔸 <b>Команда:</b>
<code>/buy ТОКЕН СУММА</code>
Например: <code>/buy USDT 10</code>
        """
        
        keyboard = [
            [InlineKeyboardButton("💎 USDT", callback_data="quick_buy_USDT"),
             InlineKeyboardButton("🔥 SCALE", callback_data="quick_buy_SCALE")],
            [InlineKeyboardButton("⚡ NOT", callback_data="quick_buy_NOT")],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(buy_text, parse_mode='HTML', reply_markup=reply_markup)
        else:
            await update.message.reply_text(buy_text, parse_mode='HTML', reply_markup=reply_markup)

    async def sell_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /sell [токен] [количество]"""
        args = context.args
        
        if len(args) >= 2:
            token_symbol = args[0].upper()
            try:
                amount = float(args[1])
                await self.execute_sell(update, token_symbol, amount)
            except ValueError:
                await update.message.reply_text("❌ Неправильное количество. Используйте: /sell USDT 1000")
        else:
            await self.show_sell_menu(update, context)

    async def show_sell_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает меню продажи"""
        try:
            # Получаем балансы для показа
            async with TonTradingEngine(self.trading_config) as engine:
                portfolio = await engine.get_portfolio()
            
            sell_text = "💸 <b>Продажа токенов</b>\n\n"
            
            if portfolio["tokens"]:
                sell_text += "🔸 <b>Ваши токены:</b>\n"
                keyboard = []
                
                for token in portfolio["tokens"]:
                    if token["balance"] > 0:
                        sell_text += f"• {token['symbol']}: {token['balance']:.2f}\n"
                        keyboard.append([InlineKeyboardButton(f"💸 {token['symbol']}", callback_data=f"quick_sell_{token['symbol']}")])
                
                sell_text += "\n🔸 <b>Команда:</b>\n<code>/sell ТОКЕН КОЛИЧЕСТВО</code>"
                keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="main_menu")])
                
            else:
                sell_text += "❌ У вас нет токенов для продажи"
                keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.callback_query:
                await update.callback_query.edit_message_text(sell_text, parse_mode='HTML', reply_markup=reply_markup)
            else:
                await update.message.reply_text(sell_text, parse_mode='HTML', reply_markup=reply_markup)
                
        except Exception as error:
            error_text = f"❌ Ошибка загрузки меню продажи: {error}"
            if update.callback_query:
                await update.callback_query.edit_message_text(error_text)
            else:
                await update.message.reply_text(error_text)

    async def execute_buy(self, update: Update, token_symbol: str, ton_amount: float):
        """Выполняет покупку токена"""
        try:
            # Проверяем, что токен существует
            if token_symbol not in self.trading_config["tokens"]:
                await update.effective_message.reply_text(
                    f"❌ Токен {token_symbol} не найден.\n"
                    f"Доступные: {', '.join(self.trading_config['tokens'].keys())}"
                )
                return

            # Отправляем уведомление о начале покупки
            processing_msg = await update.effective_message.reply_text(
                f"⏳ Выполняю покупку {token_symbol} за {ton_amount} TON...\n"
                f"🔍 Поиск лучшего маршрута..."
            )

            # Выполняем покупку
            token_address = self.trading_config["tokens"][token_symbol]
            async with TonTradingEngine(self.trading_config) as engine:
                result = await engine.buy_token(token_address, ton_amount)

            # Формируем ответ
            if result.success:
                success_text = f"""
✅ <b>Покупка успешна!</b>

💰 <b>Потрачено:</b> {ton_amount} TON
🎁 <b>Получено:</b> {result.bought_amount:.6f} {token_symbol}
💱 <b>Цена:</b> {result.price:.8f} TON за токен
🏪 <b>DEX:</b> {result.dex}
🔗 <b>TX:</b> <code>{result.tx_hash}</code>

Нажмите /portfolio для обновления баланса
                """
                
                keyboard = [
                    [InlineKeyboardButton("💼 Портфель", callback_data="portfolio")],
                    [InlineKeyboardButton("💰 Купить еще", callback_data="buy_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
            else:
                success_text = f"""
❌ <b>Ошибка покупки</b>

{result.error}

Попробуйте еще раз или обратитесь в поддержку.
                """
                keyboard = [
                    [InlineKeyboardButton("🔄 Попробовать снова", callback_data="buy_menu")],
                    [InlineKeyboardButton("💼 Портфель", callback_data="portfolio")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

            await processing_msg.edit_text(success_text, parse_mode='HTML', reply_markup=reply_markup)

        except Exception as error:
            error_text = f"❌ Критическая ошибка покупки: {error}"
            await update.effective_message.reply_text(error_text)

    async def execute_sell(self, update: Update, token_symbol: str, token_amount: float):
        """Выполняет продажу токена"""
        try:
            # Проверяем, что токен существует
            if token_symbol not in self.trading_config["tokens"]:
                await update.effective_message.reply_text(
                    f"❌ Токен {token_symbol} не найден.\n"
                    f"Доступные: {', '.join(self.trading_config['tokens'].keys())}"
                )
                return

            # Отправляем уведомление о начале продажи
            processing_msg = await update.effective_message.reply_text(
                f"⏳ Выполняю продажу {token_amount} {token_symbol}...\n"
                f"🔍 Поиск лучшего маршрута..."
            )

            # Выполняем продажу
            token_address = self.trading_config["tokens"][token_symbol]
            async with TonTradingEngine(self.trading_config) as engine:
                result = await engine.sell_token(token_address, token_amount)

            # Формируем ответ
            if result.success:
                success_text = f"""
✅ <b>Продажа успешна!</b>

💸 <b>Продано:</b> {token_amount} {token_symbol}
💰 <b>Получено:</b> {result.sold_amount:.6f} TON
💱 <b>Цена:</b> {result.price:.8f} TON за токен
🏪 <b>DEX:</b> {result.dex}
🔗 <b>TX:</b> <code>{result.tx_hash}</code>

Нажмите /portfolio для обновления баланса
                """
                
                keyboard = [
                    [InlineKeyboardButton("💼 Портфель", callback_data="portfolio")],
                    [InlineKeyboardButton("💸 Продать еще", callback_data="sell_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
            else:
                success_text = f"""
❌ <b>Ошибка продажи</b>

{result.error}

Попробуйте еще раз или обратитесь в поддержку.
                """
                keyboard = [
                    [InlineKeyboardButton("🔄 Попробовать снова", callback_data="sell_menu")],
                    [InlineKeyboardButton("💼 Портфель", callback_data="portfolio")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

            await processing_msg.edit_text(success_text, parse_mode='HTML', reply_markup=reply_markup)

        except Exception as error:
            error_text = f"❌ Критическая ошибка продажи: {error}"
            await update.effective_message.reply_text(error_text)

    async def balance_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /balance"""
        try:
            loading_msg = await update.message.reply_text("⏳ Проверяю балансы...")

            async with TonTradingEngine(self.trading_config) as engine:
                portfolio = await engine.get_portfolio()

            balance_text = "💳 <b>Ваши балансы</b>\n\n"
            
            # TON баланс
            ton_balance = portfolio["balances"].get("TON", 0)
            balance_text += f"💎 TON: {ton_balance:.6f}\n\n"
            
            # Токены
            if portfolio["tokens"]:
                balance_text += "🪙 <b>Токены:</b>\n"
                for token in portfolio["tokens"]:
                    balance_text += f"• {token['symbol']}: {token['balance']:.6f}\n"
            else:
                balance_text += "• Нет токенов\n"

            keyboard = [
                [InlineKeyboardButton("🔄 Обновить", callback_data="balance")],
                [InlineKeyboardButton("💼 Портфель", callback_data="portfolio")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await loading_msg.edit_text(balance_text, parse_mode='HTML', reply_markup=reply_markup)

        except Exception as error:
            await update.message.reply_text(f"❌ Ошибка получения балансов: {error}")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help"""
        help_text = """
❓ <b>Справка по боту</b>

<b>🔥 Основные команды:</b>
/portfolio - показать портфель
/buy ТОКЕН СУММА - купить токен
/sell ТОКЕН КОЛИЧЕСТВО - продать токен
/balance - показать балансы

<b>💰 Примеры покупки:</b>
<code>/buy USDT 10</code> - купить USDT за 10 TON
<code>/buy SCALE 5</code> - купить SCALE за 5 TON

<b>💸 Примеры продажи:</b>
<code>/sell USDT 1000</code> - продать 1000 USDT
<code>/sell SCALE 50000</code> - продать 50000 SCALE

<b>🎯 Доступные токены:</b>
• USDT - стейблкоин
• SCALE - DeFi токен
• NOT - мем токен

<b>⚠️ Важно:</b>
• Всегда проверяйте суммы перед подтверждением
• Бот автоматически находит лучшие цены
• Комиссии сети включены в расчеты
• Поддержка: @support_bot
        """
        
        keyboard = [
            [InlineKeyboardButton("💼 Портфель", callback_data="portfolio")],
            [InlineKeyboardButton("💰 Купить", callback_data="buy_menu"),
             InlineKeyboardButton("💸 Продать", callback_data="sell_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.effective_message.reply_text(help_text, parse_mode='HTML', reply_markup=reply_markup)

    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик inline кнопок"""
        query = update.callback_query
        await query.answer()

        data = query.data

        try:
            if data == "portfolio":
                await self.show_portfolio(update, context)
            elif data == "buy_menu":
                await self.show_buy_menu(update, context)
            elif data == "sell_menu":
                await self.show_sell_menu(update, context)
            elif data == "balance":
                await self.show_balance_inline(update, context)
            elif data == "help":
                await self.help_command(update, context)
            elif data.startswith("quick_buy_"):
                token_symbol = data.replace("quick_buy_", "")
                await self.initiate_quick_buy(update, context, token_symbol)
            elif data.startswith("quick_sell_"):
                token_symbol = data.replace("quick_sell_", "")
                await self.initiate_quick_sell(update, context, token_symbol)
            elif data == "main_menu":
                await self.start_command(update, context)

        except Exception as error:
            await query.edit_message_text(f"❌ Ошибка: {error}")

    async def initiate_quick_buy(self, update: Update, context: ContextTypes.DEFAULT_TYPE, token_symbol: str):
        """Инициирует быструю покупку с вводом суммы"""
        user_id = update.effective_user.id
        
        # Сохраняем сессию пользователя
        self.user_sessions[user_id] = {
            'action': 'buy',
            'token': token_symbol,
            'step': 'amount'
        }
        
        buy_text = f"""
💰 <b>Покупка {token_symbol}</b>

Введите сумму в TON для покупки {token_symbol}:

<b>Примеры:</b>
<code>1</code> - купить на 1 TON
<code>5.5</code> - купить на 5.5 TON
<code>0.1</code> - купить на 0.1 TON

Или выберите быстрые кнопки ниже:
        """
        
        keyboard = [
            [InlineKeyboardButton("0.5 TON", callback_data=f"execute_buy_{token_symbol}_0.5"),
             InlineKeyboardButton("1 TON", callback_data=f"execute_buy_{token_symbol}_1")],
            [InlineKeyboardButton("5 TON", callback_data=f"execute_buy_{token_symbol}_5"),
             InlineKeyboardButton("10 TON", callback_data=f"execute_buy_{token_symbol}_10")],
            [InlineKeyboardButton("🔙 Назад", callback_data="buy_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(buy_text, parse_mode='HTML', reply_markup=reply_markup)

    async def initiate_quick_sell(self, update: Update, context: ContextTypes.DEFAULT_TYPE, token_symbol: str):
        """Инициирует быструю продажу с выбором количества"""
        try:
            # Получаем текущий баланс токена
            token_address = self.trading_config["tokens"][token_symbol]
            async with TonTradingEngine(self.trading_config) as engine:
                balance = await engine.get_balance(token_address)

            if balance <= 0:
                await update.callback_query.edit_message_text(
                    f"❌ У вас нет {token_symbol} для продажи",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="sell_menu")]])
                )
                return

            user_id = update.effective_user.id
            self.user_sessions[user_id] = {
                'action': 'sell',
                'token': token_symbol,
                'step': 'amount',
                'max_balance': balance
            }

            sell_text = f"""
💸 <b>Продажа {token_symbol}</b>

<b>Ваш баланс:</b> {balance:.6f} {token_symbol}

Введите количество для продажи или выберите:
            """

            # Предлагаем процентные варианты
            keyboard = [
                [InlineKeyboardButton(f"25% ({balance*0.25:.2f})", callback_data=f"execute_sell_{token_symbol}_{balance*0.25:.6f}"),
                 InlineKeyboardButton(f"50% ({balance*0.5:.2f})", callback_data=f"execute_sell_{token_symbol}_{balance*0.5:.6f}")],
                [InlineKeyboardButton(f"75% ({balance*0.75:.2f})", callback_data=f"execute_sell_{token_symbol}_{balance*0.75:.6f}"),
                 InlineKeyboardButton(f"100% ({balance:.2f})", callback_data=f"execute_sell_{token_symbol}_{balance:.6f}")],
                [InlineKeyboardButton("🔙 Назад", callback_data="sell_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.callback_query.edit_message_text(sell_text, parse_mode='HTML', reply_markup=reply_markup)

        except Exception as error:
            await update.callback_query.edit_message_text(f"❌ Ошибка: {error}")

    async def show_balance_inline(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает баланс через inline кнопку"""
        try:
            async with TonTradingEngine(self.trading_config) as engine:
                portfolio = await engine.get_portfolio()

            balance_text = "💳 <b>Быстрые балансы</b>\n\n"
            balance_text += f"💎 TON: {portfolio['balances'].get('TON', 0):.6f}\n"
            
            for token in portfolio.get("tokens", []):
                balance_text += f"🪙 {token['symbol']}: {token['balance']:.6f}\n"

            keyboard = [
                [InlineKeyboardButton("🔄 Обновить", callback_data="balance")],
                [InlineKeyboardButton("💼 Подробный портфель", callback_data="portfolio")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.callback_query.edit_message_text(balance_text, parse_mode='HTML', reply_markup=reply_markup)

        except Exception as error:
            await update.callback_query.edit_message_text(f"❌ Ошибка получения балансов: {error}")

    async def message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик текстовых сообщений для диалогов"""
        user_id = update.effective_user.id
        text = update.message.text

        if user_id not in self.user_sessions:
            await update.message.reply_text(
                "💡 Используйте команды: /buy, /sell, /portfolio или /help"
            )
            return

        session = self.user_sessions[user_id]

        try:
            if session['action'] == 'buy' and session['step'] == 'amount':
                try:
                    amount = float(text)
                    if amount <= 0:
                        await update.message.reply_text("❌ Сумма должна быть больше 0")
                        return

                    # Очищаем сессию и выполняем покупку
                    token_symbol = session['token']
                    del self.user_sessions[user_id]
                    
                    await self.execute_buy(update, token_symbol, amount)

                except ValueError:
                    await update.message.reply_text("❌ Введите числовое значение. Например: 1.5")

            elif session['action'] == 'sell' and session['step'] == 'amount':
                try:
                    amount = float(text)
                    if amount <= 0:
                        await update.message.reply_text("❌ Количество должно быть больше 0")
                        return

                    if amount > session.get('max_balance', 0):
                        await update.message.reply_text(
                            f"❌ Недостаточно токенов! Максимум: {session['max_balance']:.6f}"
                        )
                        return

                    # Очищаем сессию и выполняем продажу
                    token_symbol = session['token']
                    del self.user_sessions[user_id]
                    
                    await self.execute_sell(update, token_symbol, amount)

                except ValueError:
                    await update.message.reply_text("❌ Введите числовое значение. Например: 1000")

        except Exception as error:
            if user_id in self.user_sessions:
                del self.user_sessions[user_id]
            await update.message.reply_text(f"❌ Ошибка обработки: {error}")

    def run(self):
        """Запуск Telegram бота"""
        print("🚀 Запуск Telegram Trading Bot...")
        
        application = Application.builder().token(self.telegram_token).build()

        # Регистрируем обработчики команд
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("portfolio", self.portfolio_command))
        application.add_handler(CommandHandler("buy", self.buy_command))
        application.add_handler(CommandHandler("sell", self.sell_command))
        application.add_handler(CommandHandler("balance", self.balance_command))
        application.add_handler(CommandHandler("help", self.help_command))

        # Обработчик inline кнопок
        application.add_handler(CallbackQueryHandler(self.callback_handler))
        
        # Обработчик текстовых сообщений
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.message_handler))

        # Запускаем бота
        print("✅ Telegram Bot запущен!")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

# =================== КОНФИГУРАЦИЯ И ЗАПУСК ===================

if __name__ == "__main__":
    # Конфигурация
    TELEGRAM_TOKEN = "8158233940:AAEKdtZF1M7DX7IEnJHETY7MXMaOBURb7bw"
    
    # Создаем и запускаем бота
    bot = TelegramTradingBot(TELEGRAM_TOKEN, DEMO_CONFIG)
    bot.run()