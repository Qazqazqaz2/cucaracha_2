import asyncio
import logging
from datetime import datetime, UTC
from uuid import uuid4

import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent, ChosenInlineResult
from aiogram.filters import CommandStart
from sqlalchemy import Column, String, Float, BigInteger, Integer, DateTime, Numeric, Text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.sql import select


# Config
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

BOT_TOKEN = "7620805227:AAE4pjop_z-2uFjh-B76ShT0agNzyCe22H8"
DB_DSN = "postgresql+asyncpg://postgres:762341@localhost:5432/cryptoindexator"

# DB setup
Base = declarative_base()

class Jetton(Base):
    __tablename__ = "jettons"
    id = Column(Integer, primary_key=True)
    address = Column(String, index=True)
    symbol = Column(String)
    name = Column(String)
    price_ton = Column(Float)
    price_usd = Column(Float)
    total_supply = Column(Numeric)
    decimals = Column(Integer)
    liquidity = Column(Float)
    last_checked = Column(DateTime(timezone=True))

class Pool(Base):
    __tablename__ = "pools"
    id = Column(Integer, primary_key=True)
    pool_address = Column(String, index=True)
    token0_address = Column(String)
    token1_address = Column(String)
    platform = Column(String)
    price_per_ton = Column(Float)
    lp_total_supply = Column(Numeric)
    protocol_fee_percent = Column(Float)
    last_checked = Column(DateTime(timezone=True))

# Init
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# Async DB engine
async_engine = create_async_engine(DB_DSN)
AsyncSessionLocal = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

# Handlers
@router.message(CommandStart())
async def start_handler(message):
    await message.answer("Привет! Введи @ИмяБота jetton <название> в любом чате, чтобы искать токены.")

@router.inline_query(F.query.startswith("jetton"))
async def inline_query_handler(query: InlineQuery):
    q = query.query.lower().replace("jetton", "").strip()

    async with AsyncSessionLocal() as session:
        if q:
            # Search for pools with the token symbol/name and valid TON price
            stmt = select(Pool, Jetton).join(
                Jetton, 
                ((Pool.token0_address == Jetton.address) | (Pool.token1_address == Jetton.address)) & (Jetton.address != "EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c")
            ).where(
                (Jetton.symbol.ilike(f"%{q}%")) | 
                (Jetton.name.ilike(f"%{q}%"))
            ).where(
                Pool.price_per_ton.isnot(None)
            ).limit(20)
        else:
            # Show all pools with valid TON prices
            stmt = select(Pool, Jetton).join(
                Jetton,
                ((Pool.token0_address == Jetton.address) | (Pool.token1_address == Jetton.address)) & (Jetton.address != "EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c")
            ).where(
                Pool.price_per_ton.isnot(None)
            ).limit(20)
        
        res = await session.execute(stmt)
        results_data = res.all()

    results = []
    for pool, jetton in results_data:
        if pool.price_per_ton is None:
            continue
            
        # Format the output as requested
        text = (
            f"💎 Пара: {jetton.symbol}/TON\n"
            f"🏦 Адрес пула: `{pool.pool_address}`\n"
            f"💰 Цена: {pool.price_per_ton:.6f} TON за 1 {jetton.symbol}\n"
            f"⏱️ Изм. за 10m: +0.00%\n"
            f"⌛️ Изм. за 1h: +0.00%\n"  
            f"🗓️ Изм. за 24h: +0.00%\n"
            f"📅 Изм. за 7d: +0.00%\n"
            f"📆 Изм. за 30d: +0.00%\n"
            f"🔥 Комиссия протокола: {pool.protocol_fee_percent or 0.25}% от суммы\n"
            f"📊 Ликвидность (LP supply): {int(pool.lp_total_supply) if pool.lp_total_supply else 0}"
        )
        
        results.append(
            InlineQueryResultArticle(
                id=f"{pool.id}_{jetton.id}",
                title=f"{jetton.symbol}/TON - {pool.price_per_ton:.6f} TON",
                description=f"{jetton.name} | {platform.upper()}",
                input_message_content=InputTextMessageContent(
                    message_text=text, 
                    parse_mode="Markdown"
                ),
            )
        )

    if not results:
        results.append(
            InlineQueryResultArticle(
                id="none",
                title="Ничего не найдено",
                description="Попробуй другой запрос",
                input_message_content=InputTextMessageContent(message_text="Токенов не найдено."),
            )
        )

    await query.answer(results, cache_time=30)

@router.chosen_inline_result()
async def chosen_handler(res: ChosenInlineResult):
    logger.info(f"Chosen: {res.result_id} by {res.from_user.id}")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())