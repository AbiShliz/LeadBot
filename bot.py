#!/usr/bin/env python3
import asyncio
import logging
from config import bot, dp
from handlers import *

logging.basicConfig(level=logging.INFO)

async def main():
    logging.info("🚀 LeadBot запускается...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("⛔ LeadBot остановлен")
