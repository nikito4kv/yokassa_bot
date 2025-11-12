import asyncio
import logging
import sys
from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from src.config import BOT_TOKEN
from src.handlers.user_handlers import user_router
from src.handlers.payment_handlers import payment_router
from src.handlers.group_handlers import group_router
from src.database import async_session, engine
from src.webhooks import setup_webhook_routes

async def on_startup(dispatcher: Dispatcher, bot: Bot):
    logging.info("Bot started.")

async def on_shutdown(dispatcher: Dispatcher, bot: Bot, app_runner: web.AppRunner):
    await app_runner.cleanup()
    await engine.dispose()
    logging.info("Bot and web server stopped.")

async def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    dp.include_router(payment_router)
    dp.include_router(user_router)
    dp.include_router(group_router)

    # Create aiohttp web application
    app = web.Application()
    app["bot"] = bot
    app["async_session"] = async_session
    setup_webhook_routes(app)

    # Create AppRunner
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', 8080) # You might want to change host and port
    await site.start()

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown, app_runner=runner)

    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())

