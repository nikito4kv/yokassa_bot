import asyncio
import logging
import sys
from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from functools import partial

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from src.config import BOT_TOKEN, GROUP_ID
from src.handlers.user_handlers import user_router
from src.handlers.payment_handlers import payment_router
from src.handlers.group_handlers import group_router
from src.handlers.admin_handlers import admin_router
from src.database import async_session, engine
from src.webhooks import setup_webhook_routes
from src.scheduler import check_expired_subscriptions, send_expiration_warnings

async def on_startup(bot: Bot, scheduler: AsyncIOScheduler):
    scheduler.add_job(check_expired_subscriptions, 'interval', hours=1, args=(bot, async_session))
    scheduler.add_job(send_expiration_warnings, 'interval', days=1, args=(bot, async_session))
    scheduler.start()
    logging.info("Bot and scheduler started.")

async def on_shutdown(app_runner: web.AppRunner, scheduler: AsyncIOScheduler):
    scheduler.shutdown()
    await app_runner.cleanup()
    await engine.dispose()
    logging.info("Bot, scheduler, and web server stopped.")

async def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)

    if not GROUP_ID:
        logging.error("GROUP_ID is not set in environment variables. Please set it to a valid integer.")
        sys.exit(1)
    try:
        int(GROUP_ID)
    except ValueError:
        logging.error("GROUP_ID is not a valid integer. Please set it to a valid integer.")
        sys.exit(1)

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(async_session=async_session)
    
    scheduler = AsyncIOScheduler()

    # Filter routers to only handle private messages
    user_router.message.filter(F.chat.type == "private")
    payment_router.message.filter(F.chat.type == "private")
    payment_router.callback_query.filter(F.message.chat.type == "private")

    dp.include_router(admin_router)
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
    site = web.TCPSite(runner, '0.0.0.0', 8080) 
    await site.start()

    dp.startup.register(partial(on_startup, scheduler=scheduler))
    dp.shutdown.register(partial(on_shutdown, app_runner=runner, scheduler=scheduler))

    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
        scheduler.shutdown()

if __name__ == "__main__":
    asyncio.run(main())

