import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from src.config import BOT_TOKEN
from src.handlers.user_handlers import user_router
from src.database import async_session, engine, Base
from src.models import User # Import User model for metadata

async def on_startup(dispatcher: Dispatcher, bot: Bot):
    logging.info("Bot started.")

async def on_shutdown(dispatcher: Dispatcher, bot: Bot):
    await engine.dispose()
    logging.info("Database engine disposed.")

async def main() -> None:
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    dp.include_router(user_router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    dp["async_session"] = async_session

    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
