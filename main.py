import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import BOT_TOKEN  # Импортируем API_TOKEN из config.py
from bot import register_all_handlers
from bot.utils import ensure_csv_exists, ensure_json_exists, load_places

# Настройка логирования
os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logging.info('main.py запущен')

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Запуск бота
async def main():
    # Проверяем и создаем файлы для хранения данных, если их нет
    ensure_csv_exists()
    ensure_json_exists()
    
    # Загружаем список мест для обеда
    load_places()
    
    # Регистрируем обработчики
    register_all_handlers(dp)
    
    # Запускаем бота
    await dp.start_polling(bot)

if __name__ == '__main__':
    logging.info('main.py: запуск asyncio.run(main())')
    asyncio.run(main())
