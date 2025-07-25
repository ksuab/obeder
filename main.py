import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import API_TOKEN  # Импортируем API_TOKEN из config.py
from bot import register_all_handlers
from bot.utils import ensure_csv_exists, ensure_json_exists, load_places

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
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
    asyncio.run(main())
