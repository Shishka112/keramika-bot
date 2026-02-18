import asyncio
import logging
import os
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    Message,
    FSInputFile
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

# Импортируем базу данных и каталог
from database import db
from catalog import get_catalog_items, get_item_by_id

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Константы
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "@sergeynnn03")
ADMIN_ID = os.getenv("ADMIN_ID")

# Проверка токена
if not BOT_TOKEN:
    logger.error("❌ Нет BOT_TOKEN в файле .env!")
    exit(1)

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

logger.info("✅ Бот инициализирован")

# ============= КЛАССЫ СОСТОЯНИЙ =============

class BookingStates(StatesGroup):
    """Состояния для процесса записи"""
    waiting_for_date = State()

class AdminBookingStates(StatesGroup):
    """Состояния для ручного создания записи админом"""
    waiting_for_user_id = State()
    waiting_for_username = State()
    waiting_for_name = State()
    waiting_for_booking_type = State()
    waiting_for_date = State()
    waiting_for_time = State()

# ============= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =============

def get_booking_type_name(booking_type: str) -> str:
    """Получить человекочитаемое название типа записи"""
    types = {
        "individual": "👤 Индивидуальное занятие",
        "date": "💑 Свидание (для двоих)",
        "group": "👥 Групповое занятие", 
        "school": "🏫 Школьный МК"
    }
    return types.get(booking_type, booking_type)

def get_main_menu_keyboard():
    """Главное меню"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🎨 Заказать изделие", callback_data="order_product")
    builder.button(text="🏺 Мастер-класс", callback_data="master_class")
    builder.button(text="📋 Мои записи", callback_data="my_bookings")
    builder.adjust(1)
    return builder.as_markup()

def get_dates_keyboard():
    """Клавиатура с датами на неделю вперед (со следующего дня)"""
    builder = InlineKeyboardBuilder()
    today = datetime.now()
    buttons_added = 0
    
    for i in range(1, 8):
        date = today + timedelta(days=i)
        date_str = date.strftime("%d.%m")
        
        # Проверяем занятые слоты
        booked_slots = db.get_booked_slots(date_str)
        
        if date.weekday() < 5:  # Пн-Пт
            for hour in [15, 18]:
                time_str = f"{hour}:00"
                if time_str not in booked_slots:
                    builder.button(
                        text=f"{date_str} {time_str}", 
                        callback_data=f"date_{date.strftime('%d%m')}_{hour}"
                    )
                    buttons_added += 1
        else:  # Сб-Вс
            for hour in [11, 14, 17]:
                time_str = f"{hour}:00"
                if time_str not in booked_slots:
                    builder.button(
                        text=f"{date_str} {time_str}", 
                        callback_data=f"date_{date.strftime('%d%m')}_{hour}"
                    )
                    buttons_added += 1
    
    if buttons_added == 0:
        builder.button(text="❌ Нет свободных слотов", callback_data="no_slots")
    
    builder.button(text="❌ Другая дата", callback_data="other_date")
    builder.adjust(2)
    return builder.as_markup()

def get_contact_keyboard():
    """Клавиатура для связи с администратором"""
    builder = InlineKeyboardBuilder()
    contact = ADMIN_USERNAME.replace('@', '')
    builder.button(text="💬 Написать администратору", url=f"https://t.me/{contact}")
    builder.button(text="🔙 В главное меню", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_mk_action_keyboard(mk_type: str):
    """Клавиатура действий для конкретного типа МК"""
    builder = InlineKeyboardBuilder()
    
    if mk_type == "individual":
        builder.button(text="📅 Записаться", callback_data=f"book_{mk_type}")
        builder.button(text="🎁 Подарить сертификат", callback_data="certificate_individual")
    elif mk_type == "date":
        builder.button(text="📅 Записаться на свидание", callback_data=f"book_{mk_type}")
        builder.button(text="🎁 Подарить сертификат", callback_data="certificate_date")
    elif mk_type == "group":
        builder.button(text="📅 Выбрать дату", callback_data=f"book_{mk_type}")
        builder.button(text="🎁 Подарить сертификат", callback_data="certificate_group")
    elif mk_type == "school":
        builder.button(text="📅 Выбрать дату", callback_data=f"book_{mk_type}")
    
    builder.button(text="💬 Другие вопросы", callback_data="contact_admin")
    builder.button(text="🔙 Назад", callback_data="master_class")
    builder.adjust(1)
    return builder.as_markup()

def get_catalog_keyboard(page: int = 0):
    """Клавиатура для навигации по каталогу"""
    items = get_catalog_items()
    total_pages = len(items)
    
    builder = InlineKeyboardBuilder()
    
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀️ Предыдущий", callback_data=f"catalog_page_{page-1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="Следующий ▶️", callback_data=f"catalog_page_{page+1}"))
    
    if nav_row:
        builder.row(*nav_row)
    
    current_item = items[page]
    builder.row(InlineKeyboardButton(
        text="🛒 Хочу купить этот товар", 
        callback_data=f"buy_item_{current_item['id']}"
    ))
    
    builder.row(InlineKeyboardButton(text="🔙 В меню заказа", callback_data="order_product"))
    
    return builder.as_markup()

def get_back_to_admin_keyboard():
    """Клавиатура для возврата в меню админа"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 В меню админа", callback_data="back_to_admin_menu")
    return builder.as_markup()

def get_delete_confirmation_keyboard(booking_id: int):
    """Клавиатура для подтверждения удаления записи"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, удалить", callback_data=f"delete_confirm_{booking_id}")
    builder.button(text="❌ Нет, отмена", callback_data="back_to_admin_menu")
    builder.adjust(1)
    return builder.as_markup()

# ============= ТЕКСТЫ =============

TEXTS = {
    "individual": (
        "✨ **Индивидуальное занятие за гончарным кругом**\n\n"
        "💰 **Стоимость:** 2500 рублей\n"
        "⏱ **Время:** 1–1,5 часа (30 минут закладывается на случай поломки изделия в процессе)\n\n"
        "🍽 **Об изделии:** Керамика получается пищевая, её можно использовать "
        "в духовке, микроволновке и посудомойке\n"
        "🎨 **В стоимость входит:** материалы, роспись, глазурь и 2 обжига в печи\n"
        "📦 **Готовность:** Через 2-3 недели. Отправляем домой "
        "(доставка в другой город обсуждается)\n\n"
        "⚠️ **Важно!** В мастерской живут кошки. Пожалуйста, учитывайте это, "
        "если у вас аллергия."
    ),
    
    "date": (
        "💑 **Свидание за гончарным кругом**\n\n"
        "💰 **Стоимость:** 5000 рублей (за пару)\n\n"
        "Вы скрутите в 4 руки за одним кругом вазу, блюдо, тарелку или кружки — "
        "на ваше усмотрение. Кроме вас в мастерской никого не будет, "
        "по желанию в процессе занятия можем вас фотографировать. "
        "Это будет интересная командная работа с романтикой.\n\n"
        "⏱ **Время проведения:** 1–1,5 часа (30 минут закладывается на случай "
        "поломки изделия в процессе)\n\n"
        "🍽 **Об изделии:** Керамика получается пищевая, её можно использовать "
        "в духовке, микроволновке и посудомойке\n\n"
        "🎨 **В стоимость мастер-класса уже входят:**\n"
        "• Все материалы\n"
        "• Роспись\n"
        "• Покрытие глазурью\n"
        "• 2 обжига в печи\n\n"
        "📦 **Готовность:** Изделие будет готово через 2-3 недели, после чего "
        "отправляется к вам домой. Если вы из другого города, мы можем оформить доставку.\n\n"
        "⚠️ **Сразу хочу предупредить, это важно:** В мастерской живут кошки. "
        "Имейте в виду, на случай, если у вас аллергия."
    ),
    
    "group": (
        "👥 **Групповое занятие**\n\n"
        "💰 **Стоимость:** 2000 рублей с человека\n\n"
        "Вы можете слепить/скрутить утилитарное или декоративное изделие: "
        "чашку, тарелку, вазу.\n\n"
        "👨‍👩‍👧‍👦 **Размер группы:** Для комфорта желательно, чтобы группа была "
        "не больше 10 человек, но мы всегда готовы пойти навстречу и обсудить ваш вариант.\n\n"
        "⏱ **Время:** 1–1,5 часа\n\n"
        "🎨 **В стоимость входит:**\n"
        "• Все материалы\n"
        "• Роспись\n"
        "• Покрытие глазурью\n"
        "• 2 обжига в печи\n\n"
        "🍽 Керамику можно использовать в быту, она пищевая, можно ставить "
        "в духовку/микроволновку/посудомойку\n\n"
        "📦 Изделие будет готово через 2-3 недели, после чего отправляется к вам домой.\n\n"
        "⚠️ **Важно!** В мастерской живут кошки."
    ),
    
    "school": (
        "🏫 **Мастер-класс для школьников**\n\n"
        "💰 **Стоимость:** 800 рублей с человека\n\n"
        "На занятии дети работают за раскаточным станком, делают тарелку с оттиском "
        "или орнаментом и сразу ее расписывают.\n\n"
        "⏱ **Время занятия:** 1–1,5 часа\n\n"
        "🔥 **Технология:** Изделие остается у меня на 2-3 недели, сохнет, после чего "
        "я ставлю первый обжиг, покрываю глазурью (стеклом) и ставлю на второй обжиг. "
        "Керамика обжигается при температуре 1150 градусов, поэтому изделие будет "
        "утилитарное и крепкое.\n\n"
        "🎨 **В стоимость мастер-класса уже входят:**\n"
        "• Все материалы\n"
        "• Покрытие глазурью\n"
        "• 2 обжига в печи"
    ),
    
    "certificate": (
        "🎁 **Подарочный сертификат в «Керамику Юноны»**\n\n"
        "Вы можете подарить близкому человеку сертификат на занятие:\n"
        "• Индивидуальное (2500₽)\n"
        "• Свидание (5000₽ за пару)\n"
        "• Групповое (2000₽/чел)\n\n"
        "Напишите администратору, и мы поможем с выбором номинала и оформлением."
    )
}

# ============= ПЛАНИРОВЩИК НАПОМИНАНИЙ =============

async def check_reminders():
    """Проверка и отправка напоминаний (запускается каждые 15 минут)"""
    while True:
        try:
            now = datetime.now()
            current_time = now.strftime("%H:%M")
            current_date = now.strftime("%d.%m")
            
            logger.info(f"⏰ Проверка напоминаний: {current_date} {current_time}")
            
            # Получаем все подтвержденные записи
            all_bookings = db.get_confirmed_bookings()
            
            for booking in all_bookings:
                try:
                    # Парсим дату и время записи
                    booking_date = booking['selected_date']
                    booking_time = booking['selected_time']
                    
                    # Пропускаем, если запись не на сегодня или позже
                    if booking_date < current_date:
                        continue
                    
                    # Преобразуем в datetime для сравнения
                    date_parts = booking_date.split('.')
                    time_parts = booking_time.split(':')
                    
                    if len(date_parts) != 2 or len(time_parts) != 2:
                        continue
                    
                    booking_datetime = datetime(
                        now.year, int(date_parts[1]), int(date_parts[0]),
                        int(time_parts[0]), int(time_parts[1])
                    )
                    
                    # Разница в часах до начала
                    hours_diff = (booking_datetime - now).total_seconds() / 3600
                    
                    # НАПОМИНАНИЕ ЗА ДЕНЬ (24 часа)
                    if 23 <= hours_diff <= 25 and not booking.get('reminder_day_sent', 0):
                        await send_day_reminder(booking)
                        db.mark_reminder_sent(booking['id'], 'day')
                        logger.info(f"📨 Отправлено дневное напоминание для записи #{booking['id']}")
                    
                    # НАПОМИНАНИЕ ЗА ЧАС
                    elif 0.9 <= hours_diff <= 1.1 and not booking.get('reminder_hour_sent', 0):
                        await send_hour_reminder(booking)
                        db.mark_reminder_sent(booking['id'], 'hour')
                        logger.info(f"📨 Отправлено часовое напоминание для записи #{booking['id']}")
                    
                    # НАПОМИНАНИЕ АДМИНУ ЗА ЧАС
                    if 0.9 <= hours_diff <= 1.1:
                        await send_admin_reminder(booking)
                        
                except Exception as e:
                    logger.error(f"Ошибка при обработке напоминания для записи #{booking.get('id')}: {e}")
            
        except Exception as e:
            logger.error(f"Ошибка в планировщике напоминаний: {e}")
        
        # Проверяем каждые 15 минут
        await asyncio.sleep(900)

async def send_day_reminder(booking: dict):
    """Отправка напоминания за день"""
    try:
        text = (
            f"🔔 **Напоминание о мастер-классе!**\n\n"
            f"🎯 {get_booking_type_name(booking['booking_type'])}\n"
            f"📅 Завтра, {booking['selected_date']} в {booking['selected_time']}\n\n"
            f"Ждем вас в мастерской! Если возникнут вопросы, свяжитесь с администратором."
        )
        
        await bot.send_message(
            booking['user_id'],
            text,
            parse_mode="Markdown",
            reply_markup=get_contact_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка отправки дневного напоминания: {e}")

async def send_hour_reminder(booking: dict):
    """Отправка напоминания за час"""
    try:
        text = (
            f"⏰ **Через час начинается мастер-класс!**\n\n"
            f"🎯 {get_booking_type_name(booking['booking_type'])}\n"
            f"📅 Сегодня, {booking['selected_date']} в {booking['selected_time']}\n\n"
            f"Уже выходите? Ждем вас! 🏺"
        )
        
        await bot.send_message(
            booking['user_id'],
            text,
            parse_mode="Markdown",
            reply_markup=get_contact_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка отправки часового напоминания: {e}")

async def send_admin_reminder(booking: dict):
    """Отправка напоминания администратору за час"""
    if not ADMIN_ID:
        return
    
    try:
        text = (
            f"⏰ **Через час мастер-класс!**\n\n"
            f"👤 {booking['full_name']} (@{booking['username']})\n"
            f"🎯 {get_booking_type_name(booking['booking_type'])}\n"
            f"📅 Сегодня, {booking['selected_date']} в {booking['selected_time']}\n\n"
            f"Не забудьте подготовить материалы! 🏺"
        )
        
        await bot.send_message(
            int(ADMIN_ID),
            text,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Ошибка отправки напоминания админу: {e}")

# ============= ОБРАБОТЧИКИ КОМАНД =============

@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    logger.info(f"🔥 /start от {message.from_user.id}")
    await message.answer(
        "✨ Добрый день! Это «Керамика Юноны»\n\n"
        "Подскажите, вас интересует мастер-класс или хотите заказать готовое изделие?",
        reply_markup=get_main_menu_keyboard()
    )

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    """Команда для администратора - просмотр неподтвержденных заявок"""
    if str(message.from_user.id) != str(ADMIN_ID):
        await message.answer("⛔ У вас нет прав администратора")
        return
    
    pending = db.get_pending_bookings()
    
    if not pending:
        await message.answer("📭 Нет неподтвержденных заявок")
        return
    
    for booking in pending[:5]:
        text = (
            f"📝 **Заявка #{booking['id']}**\n"
            f"👤 {booking['full_name']} (@{booking['username']})\n"
            f"🎯 {get_booking_type_name(booking['booking_type'])}\n"
            f"📅 {booking['selected_date']} {booking['selected_time']}\n"
            f"⏰ Создана: {booking['created_at']}"
        )
        
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="✅ Подтвердить", callback_data=f"confirm_{booking['id']}")
        keyboard.button(text="❌ Отклонить", callback_data=f"reject_{booking['id']}")
        keyboard.button(text="🗑 Удалить", callback_data=f"admin_delete_{booking['id']}")
        keyboard.adjust(2, 1)
        
        await message.answer(text, parse_mode="Markdown", reply_markup=keyboard.as_markup())

@dp.message(Command("bookings"))
async def cmd_bookings(message: Message):
    """Команда для просмотра всех записей"""
    if str(message.from_user.id) != str(ADMIN_ID):
        await message.answer("⛔ У вас нет прав администратора")
        return
    
    all_bookings = db.get_all_bookings()
    summary = db.get_bookings_summary()
    
    if not all_bookings:
        await message.answer("📭 В базе нет записей")
        return
    
    # Отправляем статистику
    summary_text = (
        f"📊 **Статистика записей:**\n\n"
        f"⏳ Ожидают подтверждения: {summary['pending']}\n"
        f"✅ Подтверждено: {summary['confirmed']}\n"
        f"❌ Отклонено: {summary['rejected']}\n"
        f"📝 Всего: {summary['total']}"
    )
    await message.answer(summary_text, parse_mode="Markdown")
    
    # Создаем клавиатуру с кнопками
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="📅 Сегодня", callback_data="admin_today")
    keyboard.button(text="📅 Неделя", callback_data="admin_week")
    keyboard.button(text="📋 Все записи", callback_data="admin_all")
    keyboard.button(text="⏳ Ожидающие", callback_data="admin_pending")
    keyboard.button(text="➕ Ручная запись", callback_data="admin_manual_booking")
    keyboard.button(text="🗑 Удалить запись", callback_data="admin_delete_menu")
    keyboard.adjust(2)
    
    await message.answer(
        "📌 **Меню администратора:**\n\n"
        "Выберите действие:",
        parse_mode="Markdown",
        reply_markup=keyboard.as_markup()
    )

@dp.message(Command("add_booking"))
async def cmd_add_booking(message: Message, state: FSMContext):
    """Команда для ручного добавления записи администратором"""
    if str(message.from_user.id) != str(ADMIN_ID):
        await message.answer("⛔ У вас нет прав администратора")
        return
    
    await message.answer(
        "📝 **Ручное создание записи**\n\n"
        "Введите ID пользователя в Telegram (число):\n"
        "Если не знаете ID, введите 0 и мы запросим username",
        parse_mode="Markdown"
    )
    await state.set_state(AdminBookingStates.waiting_for_user_id)

# ============= ОБРАБОТЧИКИ КОЛЛБЭКОВ =============

@dp.callback_query(lambda c: c.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    """Возврат в главное меню"""
    await callback.message.delete()
    await callback.message.answer(
        "✨ Добрый день! Это «Керамика Юноны»\n\n"
        "Подскажите, вас интересует мастер-класс или хотите заказать готовое изделие?",
        reply_markup=get_main_menu_keyboard()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "order_product")
async def order_product(callback: CallbackQuery):
    """Заказ изделий"""
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="👀 Посмотреть наличие", callback_data="check_stock")
    keyboard.button(text="✍️ Заказ по референсу", callback_data="order_reference")
    keyboard.button(text="🔙 Назад", callback_data="back_to_main")
    keyboard.adjust(1)
    
    await callback.message.delete()
    await callback.message.answer(
        "В разделе «Изделия» вы можете:\n\n"
        "👀 **Посмотреть наличие** — фото готовых работ\n"
        "✍️ **Сделать заказ по своему референсу** — обсудим детали",
        parse_mode="Markdown",
        reply_markup=keyboard.as_markup()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "check_stock")
async def check_stock(callback: CallbackQuery):
    """Просмотр каталога"""
    items = get_catalog_items()
    
    if not items:
        await callback.message.delete()
        await callback.message.answer(
            "😔 В данный момент товаров нет в наличии",
            reply_markup=get_contact_keyboard()
        )
        await callback.answer()
        return
    
    await callback.message.delete()
    await show_catalog_item(callback.message, 0)
    await callback.answer()

async def show_catalog_item(message: Message, page: int):
    """Отображение товара"""
    items = get_catalog_items()
    
    if page < 0 or page >= len(items):
        page = 0
    
    item = items[page]
    
    caption = (
        f"🖼 **{item['name']}**\n\n"
        f"{item['description']}\n\n"
        f"💰 **Цена:** {item['price']} ₽\n\n"
        f"Товар {page + 1} из {len(items)}"
    )
    
    try:
        photo = FSInputFile(item['image'])
        await message.answer_photo(
            photo=photo,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=get_catalog_keyboard(page)
        )
    except Exception as e:
        logger.error(f"Ошибка с фото: {e}")
        await message.answer(
            caption,
            parse_mode="Markdown",
            reply_markup=get_catalog_keyboard(page)
        )

@dp.callback_query(lambda c: c.data.startswith("catalog_page_"))
async def catalog_navigation(callback: CallbackQuery):
    """Навигация по каталогу"""
    page = int(callback.data.replace("catalog_page_", ""))
    await callback.message.delete()
    await show_catalog_item(callback.message, page)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("buy_item_"))
async def buy_item(callback: CallbackQuery):
    """Покупка товара"""
    item_id = int(callback.data.replace("buy_item_", ""))
    item = get_item_by_id(item_id)
    
    if not item:
        await callback.answer("❌ Товар не найден", show_alert=True)
        return
    
    user = callback.from_user
    
    admin_text = (
        f"🛒 **Запрос на покупку!**\n\n"
        f"👤 {user.full_name or 'Имя'}\n"
        f"🆔 ID: {user.id}\n"
        f"📱 @{user.username if user.username else 'нет'}\n\n"
        f"🎁 {item['name']}\n"
        f"💰 {item['price']} ₽"
    )
    
    if ADMIN_ID:
        try:
            await bot.send_message(int(ADMIN_ID), admin_text, parse_mode="Markdown")
            logger.info(f"Уведомление о покупке #{item_id} отправлено")
        except Exception as e:
            logger.error(f"Ошибка уведомления: {e}")
    
    await callback.message.delete()
    await callback.message.answer(
        f"✅ **Запрос отправлен!**\n\n"
        f"Товар: **{item['name']}**\n\n"
        f"Скоро администратор свяжется с вами.",
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "order_reference")
async def order_reference(callback: CallbackQuery):
    """Заказ по референсу"""
    await callback.message.delete()
    await callback.message.answer(
        "У вас есть фото или идея? Пришлите их администратору.",
        reply_markup=get_contact_keyboard()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "master_class")
async def master_class(callback: CallbackQuery):
    """Меню мастер-классов"""
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="👤 Индивидуально", callback_data="mk_individual")
    keyboard.button(text="💑 Свидание", callback_data="mk_date")
    keyboard.button(text="👥 Групповое", callback_data="mk_group")
    keyboard.button(text="🏫 Школьный", callback_data="mk_school")
    keyboard.button(text="🎁 Сертификат", callback_data="mk_certificate")
    keyboard.button(text="🔙 Назад", callback_data="back_to_main")
    keyboard.adjust(1)
    
    await callback.message.delete()
    await callback.message.answer(
        "Выберите формат мастер-класса:",
        reply_markup=keyboard.as_markup()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("mk_"))
async def show_mk_details(callback: CallbackQuery):
    """Детали мастер-класса"""
    mk_type = callback.data.replace("mk_", "")
    
    if mk_type == "certificate":
        text = TEXTS["certificate"]
        keyboard = get_contact_keyboard()
    else:
        text = TEXTS.get(mk_type, "Информация недоступна")
        keyboard = get_mk_action_keyboard(mk_type)
    
    await callback.message.delete()
    await callback.message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("book_"))
async def start_booking(callback: CallbackQuery, state: FSMContext):
    """Начало записи"""
    booking_type = callback.data.replace("book_", "")
    await state.update_data(booking_type=booking_type)
    await state.set_state(BookingStates.waiting_for_date)
    
    await callback.message.delete()
    await callback.message.answer(
        "📅 **Выберите дату и время:**\n\n"
        "Доступные слоты на ближайшие 7 дней:",
        parse_mode="Markdown",
        reply_markup=get_dates_keyboard()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("date_"), BookingStates.waiting_for_date)
async def process_booking(callback: CallbackQuery, state: FSMContext):
    """Обработка выбранной даты"""
    try:
        data = await state.get_data()
        booking_type = data.get("booking_type", "individual")
        
        parts = callback.data.split("_")
        day = parts[1][:2]
        month = parts[1][2:]
        hour = parts[2]
        
        selected_date = f"{day}.{month}"
        selected_time = f"{hour}:00"
        
        if not db.is_slot_available(selected_date, selected_time):
            await callback.answer("❌ Это время уже занято!", show_alert=True)
            return
        
        user = callback.from_user
        booking_id = db.create_booking(
            user_id=user.id,
            username=user.username or "нет",
            full_name=user.full_name or "Имя",
            booking_type=booking_type,
            date=selected_date,
            time=selected_time
        )
        
        logger.info(f"✅ Заявка #{booking_id} создана")
        
        if ADMIN_ID:
            admin_keyboard = InlineKeyboardBuilder()
            admin_keyboard.button(text="✅ Подтвердить", callback_data=f"confirm_{booking_id}")
            admin_keyboard.button(text="❌ Отклонить", callback_data=f"reject_{booking_id}")
            admin_keyboard.adjust(2)
            
            admin_text = (
                f"📝 **Новая заявка!**\n\n"
                f"👤 {user.full_name}\n"
                f"🆔 {user.id}\n"
                f"📱 @{user.username}\n"
                f"🎯 {get_booking_type_name(booking_type)}\n"
                f"📅 {selected_date}\n"
                f"⏰ {selected_time}"
            )
            
            await bot.send_message(
                int(ADMIN_ID),
                admin_text,
                parse_mode="Markdown",
                reply_markup=admin_keyboard.as_markup()
            )
        
        await state.clear()
        await callback.answer("✅ Заявка создана!")
        await callback.message.delete()
        await callback.message.answer(
            f"✅ **Заявка создана!**\n\n"
            f"📅 {selected_date} в {selected_time}\n"
            f"🎯 {get_booking_type_name(booking_type)}\n\n"
            f"⏳ Ожидайте подтверждения.",
            parse_mode="Markdown",
            reply_markup=get_main_menu_keyboard()
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)
        await state.clear()

@dp.callback_query(lambda c: c.data.startswith("confirm_"))
async def confirm_booking(callback: CallbackQuery):
    """Подтверждение записи"""
    if str(callback.from_user.id) != str(ADMIN_ID):
        await callback.answer("⛔ Нет прав", show_alert=True)
        return
    
    booking_id = int(callback.data.replace("confirm_", ""))
    booking = db.get_booking(booking_id)
    
    if not booking:
        await callback.answer("❌ Не найдено", show_alert=True)
        return
    
    db.update_booking_status(booking_id, 'confirmed')
    
    try:
        await bot.send_message(
            booking['user_id'],
            f"✅ **Ваша запись подтверждена!**\n\n"
            f"📅 {booking['selected_date']} {booking['selected_time']}\n"
            f"🎯 {get_booking_type_name(booking['booking_type'])}\n\n"
            f"Ждем вас!",
            parse_mode="Markdown",
            reply_markup=get_contact_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка уведомления: {e}")
    
    await callback.answer("✅ Подтверждено")
    await callback.message.edit_text(f"{callback.message.text}\n\n✅ **ПОДТВЕРЖДЕНО**")

@dp.callback_query(lambda c: c.data.startswith("reject_"))
async def reject_booking(callback: CallbackQuery):
    """Отклонение записи"""
    if str(callback.from_user.id) != str(ADMIN_ID):
        await callback.answer("⛔ Нет прав", show_alert=True)
        return
    
    booking_id = int(callback.data.replace("reject_", ""))
    booking = db.get_booking(booking_id)
    
    if not booking:
        await callback.answer("❌ Не найдено", show_alert=True)
        return
    
    db.update_booking_status(booking_id, 'rejected')
    
    try:
        await bot.send_message(
            booking['user_id'],
            f"❌ **К сожалению, выбранное время недоступно**\n\n"
            f"Свяжитесь с администратором.",
            parse_mode="Markdown",
            reply_markup=get_contact_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка уведомления: {e}")
    
    await callback.answer("❌ Отклонено")
    await callback.message.edit_text(f"{callback.message.text}\n\n❌ **ОТКЛОНЕНО**")

@dp.callback_query(lambda c: c.data == "my_bookings")
async def show_my_bookings(callback: CallbackQuery):
    """Мои записи"""
    bookings = db.get_user_bookings(callback.from_user.id)
    
    if not bookings:
        await callback.message.delete()
        await callback.message.answer(
            "📭 У вас пока нет записей",
            reply_markup=get_main_menu_keyboard()
        )
        await callback.answer()
        return
    
    text = "📋 **Ваши записи:**\n\n"
    for booking in bookings[:5]:
        status_emoji = {
            'pending': '⏳',
            'confirmed': '✅',
            'rejected': '❌'
        }.get(booking['status'], '❓')
        
        text += (
            f"{status_emoji} {get_booking_type_name(booking['booking_type'])}\n"
            f"   📅 {booking['selected_date']} {booking['selected_time']}\n"
            f"   Статус: {booking['status']}\n\n"
        )
    
    text += "Статусы: ⏳ ожидание, ✅ подтверждено, ❌ отклонено"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔙 Назад", callback_data="back_to_main")
    
    await callback.message.delete()
    await callback.message.answer(text, parse_mode="Markdown", reply_markup=keyboard.as_markup())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "other_date")
async def other_date(callback: CallbackQuery):
    """Другая дата"""
    await callback.message.delete()
    await callback.message.answer(
        "Напишите администратору для выбора другой даты",
        reply_markup=get_contact_keyboard()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "no_slots")
async def no_slots(callback: CallbackQuery):
    """Нет слотов"""
    await callback.answer("❌ На ближайшую неделю нет свободных мест", show_alert=True)

@dp.callback_query(lambda c: c.data == "contact_admin")
async def contact_admin(callback: CallbackQuery):
    """Связь с админом"""
    await callback.message.delete()
    await callback.message.answer(
        "Задайте вопрос напрямую мастеру:",
        reply_markup=get_contact_keyboard()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("certificate_"))
async def handle_certificate(callback: CallbackQuery):
    """Сертификаты"""
    cert_type = callback.data.replace("certificate_", "")
    
    names = {
        "individual": "индивидуальное",
        "date": "свидание", 
        "group": "групповое"
    }
    
    await callback.message.delete()
    await callback.message.answer(
        f"🎁 Сертификат на **{names.get(cert_type, 'занятие')}**\n"
        "Напишите администратору для оформления.",
        parse_mode="Markdown",
        reply_markup=get_contact_keyboard()
    )
    await callback.answer()

# ============= ОБРАБОТЧИКИ ДЛЯ РУЧНОГО СОЗДАНИЯ ЗАПИСИ =============

@dp.message(AdminBookingStates.waiting_for_user_id)
async def process_admin_user_id(message: Message, state: FSMContext):
    """Обработка ввода ID пользователя"""
    try:
        user_id = int(message.text)
        await state.update_data(user_id=user_id)
        
        if user_id == 0:
            await message.answer(
                "Введите username пользователя (без @):\n"
                "Например: sergeynnn03"
            )
            await state.set_state(AdminBookingStates.waiting_for_username)
        else:
            await message.answer(
                "Введите имя пользователя (ФИО или как записать):"
            )
            await state.set_state(AdminBookingStates.waiting_for_name)
    except ValueError:
        await message.answer("❌ Нужно ввести число. Попробуйте еще раз:")

@dp.message(AdminBookingStates.waiting_for_username)
async def process_admin_username(message: Message, state: FSMContext):
    """Обработка ввода username"""
    username = message.text.replace('@', '')
    await state.update_data(username=username)
    
    await message.answer(
        "Введите имя пользователя (ФИО или как записать):"
    )
    await state.set_state(AdminBookingStates.waiting_for_name)

@dp.message(AdminBookingStates.waiting_for_name)
async def process_admin_name(message: Message, state: FSMContext):
    """Обработка ввода имени"""
    await state.update_data(full_name=message.text)
    
    # Создаем клавиатуру с типами занятий
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="👤 Индивидуальное", callback_data="admin_book_individual")
    keyboard.button(text="💑 Свидание", callback_data="admin_book_date")
    keyboard.button(text="👥 Групповое", callback_data="admin_book_group")
    keyboard.button(text="🏫 Школьный", callback_data="admin_book_school")
    keyboard.button(text="❌ Отмена", callback_data="admin_cancel_booking")
    keyboard.adjust(2)
    
    await message.answer(
        "Выберите тип занятия:",
        reply_markup=keyboard.as_markup()
    )
    await state.set_state(AdminBookingStates.waiting_for_booking_type)

@dp.callback_query(lambda c: c.data.startswith("admin_book_"), AdminBookingStates.waiting_for_booking_type)
async def process_admin_booking_type(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора типа занятия"""
    booking_type = callback.data.replace("admin_book_", "")
    
    if booking_type == "cancel":
        await state.clear()
        await callback.message.edit_text("❌ Создание записи отменено")
        await callback.answer()
        return
    
    await state.update_data(booking_type=booking_type)
    
    await callback.message.delete()
    await callback.message.answer(
        "📅 **Выберите дату:**\n\n"
        "Введите дату в формате ДД.ММ\n"
        "Например: 25.02",
        parse_mode="Markdown"
    )
    await state.set_state(AdminBookingStates.waiting_for_date)
    await callback.answer()

@dp.message(AdminBookingStates.waiting_for_date)
async def process_admin_date(message: Message, state: FSMContext):
    """Обработка ввода даты"""
    date = message.text.strip()
    
    # Простая проверка формата
    if len(date) != 5 or date[2] != '.':
        await message.answer("❌ Неправильный формат. Используйте ДД.ММ (например: 25.02)")
        return
    
    await state.update_data(selected_date=date)
    
    await message.answer(
        "⏰ **Выберите время:**\n\n"
        "Введите время в формате ЧЧ:ММ\n"
        "Например: 15:00 или 18:00",
        parse_mode="Markdown"
    )
    await state.set_state(AdminBookingStates.waiting_for_time)

@dp.message(AdminBookingStates.waiting_for_time)
async def process_admin_time(message: Message, state: FSMContext):
    """Обработка ввода времени и создание записи"""
    try:
        time_str = message.text.strip()
        
        # Простая проверка формата
        if len(time_str) != 5 or time_str[2] != ':':
            await message.answer("❌ Неправильный формат. Используйте ЧЧ:ММ (например: 15:00)")
            return
        
        data = await state.get_data()
        
        user_id = data.get('user_id', 0)
        username = data.get('username', 'manual')
        full_name = data.get('full_name', 'Ручная запись')
        booking_type = data.get('booking_type', 'individual')
        selected_date = data.get('selected_date')
        
        # Проверяем, свободен ли слот
        if not db.is_slot_available(selected_date, time_str):
            await message.answer(
                f"❌ Слот {selected_date} {time_str} уже занят!\n"
                f"Выберите другое время командой /add_booking"
            )
            await state.clear()
            return
        
        # Создаем запись
        booking_id = db.create_booking(
            user_id=user_id,
            username=username,
            full_name=full_name,
            booking_type=booking_type,
            date=selected_date,
            time=time_str
        )
        
        # Сразу подтверждаем запись (админ же сам записал)
        db.update_booking_status(booking_id, 'confirmed')
        
        logger.info(f"✅ Ручная запись #{booking_id} создана админом")
        
        # Отправляем подтверждение
        await message.answer(
            f"✅ **Запись успешно создана!**\n\n"
            f"🆔 **ID записи:** {booking_id}\n"
            f"👤 **Клиент:** {full_name}\n"
            f"📱 **Username:** @{username if username != 'manual' else 'не указан'}\n"
            f"🎯 **Тип:** {get_booking_type_name(booking_type)}\n"
            f"📅 **Дата:** {selected_date}\n"
            f"⏰ **Время:** {time_str}\n\n"
            f"Статус: ✅ Подтверждено",
            parse_mode="Markdown"
        )
        
        # Если есть реальный user_id, отправляем уведомление пользователю
        if user_id and user_id != 0:
            try:
                await bot.send_message(
                    user_id,
                    f"✅ **Вы записаны на мастер-класс!**\n\n"
                    f"🎯 {get_booking_type_name(booking_type)}\n"
                    f"📅 {selected_date} в {time_str}\n\n"
                    f"Ждем вас в мастерской!",
                    parse_mode="Markdown",
                    reply_markup=get_contact_keyboard()
                )
                await message.answer("📨 Уведомление отправлено пользователю")
            except Exception as e:
                await message.answer(f"⚠️ Не удалось отправить уведомление пользователю: {e}")
        
    except Exception as e:
        logger.error(f"Ошибка при ручном создании записи: {e}")
        await message.answer(f"❌ Ошибка: {e}")
    
    await state.clear()

@dp.callback_query(lambda c: c.data == "admin_cancel_booking")
async def admin_cancel_booking(callback: CallbackQuery, state: FSMContext):
    """Отмена ручного создания записи"""
    await state.clear()
    await callback.message.edit_text("❌ Создание записи отменено")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_manual_booking")
async def admin_manual_booking(callback: CallbackQuery, state: FSMContext):
    """Начало ручного создания записи из меню"""
    if str(callback.from_user.id) != str(ADMIN_ID):
        await callback.answer("⛔ У вас нет прав", show_alert=True)
        return
    
    await callback.message.delete()
    await callback.message.answer(
        "📝 **Ручное создание записи**\n\n"
        "Введите ID пользователя в Telegram (число):\n"
        "Если не знаете ID, введите 0 и мы запросим username",
        parse_mode="Markdown"
    )
    await state.set_state(AdminBookingStates.waiting_for_user_id)
    await callback.answer()

# ============= ОБРАБОТЧИКИ ДЛЯ УДАЛЕНИЯ ЗАПИСЕЙ =============

@dp.callback_query(lambda c: c.data == "admin_delete_menu")
async def admin_delete_menu(callback: CallbackQuery):
    """Меню удаления записей"""
    if str(callback.from_user.id) != str(ADMIN_ID):
        await callback.answer("⛔ У вас нет прав", show_alert=True)
        return
    
    # Показываем последние 10 записей для удаления
    all_bookings = db.get_all_bookings()
    
    if not all_bookings:
        await callback.message.edit_text(
            "📭 Нет записей для удаления",
            reply_markup=get_back_to_admin_keyboard()
        )
        await callback.answer()
        return
    
    text = "🗑 **Выберите запись для удаления:**\n\n"
    
    keyboard = InlineKeyboardBuilder()
    
    for booking in all_bookings[:10]:
        status_emoji = {
            'pending': '⏳',
            'confirmed': '✅',
            'rejected': '❌'
        }.get(booking['status'], '❓')
        
        short_name = booking['full_name'][:15] + "..." if len(booking['full_name']) > 15 else booking['full_name']
        
        button_text = f"{status_emoji} #{booking['id']} {booking['selected_date']} {short_name}"
        keyboard.button(text=button_text, callback_data=f"admin_delete_{booking['id']}")
    
    keyboard.button(text="🔙 Назад", callback_data="back_to_admin_menu")
    keyboard.adjust(1)
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=keyboard.as_markup()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("admin_delete_"))
async def admin_delete_booking(callback: CallbackQuery):
    """Подтверждение удаления записи"""
    if str(callback.from_user.id) != str(ADMIN_ID):
        await callback.answer("⛔ У вас нет прав", show_alert=True)
        return
    
    booking_id = int(callback.data.replace("admin_delete_", ""))
    booking = db.get_booking(booking_id)
    
    if not booking:
        await callback.answer("❌ Запись не найдена", show_alert=True)
        return
    
    text = (
        f"🗑 **Подтверждение удаления**\n\n"
        f"Вы уверены, что хотите удалить запись?\n\n"
        f"🆔 **ID:** {booking['id']}\n"
        f"👤 **Клиент:** {booking['full_name']}\n"
        f"📱 **Username:** @{booking['username']}\n"
        f"🎯 **Тип:** {get_booking_type_name(booking['booking_type'])}\n"
        f"📅 **Дата:** {booking['selected_date']}\n"
        f"⏰ **Время:** {booking['selected_time']}\n"
        f"📊 **Статус:** {booking['status']}"
    )
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_delete_confirmation_keyboard(booking_id)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("delete_confirm_"))
async def delete_confirm(callback: CallbackQuery):
    """Окончательное удаление записи"""
    if str(callback.from_user.id) != str(ADMIN_ID):
        await callback.answer("⛔ У вас нет прав", show_alert=True)
        return
    
    booking_id = int(callback.data.replace("delete_confirm_", ""))
    booking = db.get_booking(booking_id)
    
    if not booking:
        await callback.answer("❌ Запись не найдена", show_alert=True)
        return
    
    # Удаляем запись
    success = db.delete_booking(booking_id)
    
    if success:
        logger.info(f"🗑 Запись #{booking_id} удалена админом")
        
        # Отправляем уведомление пользователю, если есть user_id
        if booking['user_id'] and booking['user_id'] != 0:
            try:
                await bot.send_message(
                    booking['user_id'],
                    f"❌ **Ваша запись была отменена**\n\n"
                    f"К сожалению, запись на {booking['selected_date']} в {booking['selected_time']} "
                    f"была отменена. Свяжитесь с администратором для уточнения деталей.",
                    parse_mode="Markdown",
                    reply_markup=get_contact_keyboard()
                )
            except Exception as e:
                logger.error(f"Ошибка при уведомлении пользователя об удалении: {e}")
        
        await callback.message.edit_text(
            f"✅ **Запись #{booking_id} успешно удалена**",
            reply_markup=get_back_to_admin_keyboard()
        )
    else:
        await callback.message.edit_text(
            "❌ **Ошибка при удалении записи**",
            reply_markup=get_back_to_admin_keyboard()
        )
    
    await callback.answer()

# ============= ОБРАБОТЧИКИ ДЛЯ АДМИНА (ПРОСМОТР ЗАПИСЕЙ) =============

@dp.callback_query(lambda c: c.data == "admin_today")
async def admin_today(callback: CallbackQuery):
    """Записи на сегодня"""
    if str(callback.from_user.id) != str(ADMIN_ID):
        await callback.answer("⛔ У вас нет прав", show_alert=True)
        return
    
    today = datetime.now().strftime("%d.%m")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d.%m")
    
    bookings = db.get_bookings_by_date_range(today, tomorrow)
    
    if not bookings:
        await callback.message.edit_text(
            "📭 На сегодня нет записей",
            reply_markup=get_back_to_admin_keyboard()
        )
        await callback.answer()
        return
    
    text = f"📅 **Записи на {today}:**\n\n"
    for b in bookings:
        status_emoji = "✅" if b['status'] == 'confirmed' else "⏳"
        text += (
            f"{status_emoji} {b['selected_time']} - {b['full_name']}\n"
            f"   🎯 {get_booking_type_name(b['booking_type'])}\n"
            f"   📱 @{b['username']}\n"
            f"   🆔 #{b['id']}\n\n"
        )
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔙 Назад", callback_data="back_to_admin_menu")
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard.as_markup())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_week")
async def admin_week(callback: CallbackQuery):
    """Записи на неделю"""
    if str(callback.from_user.id) != str(ADMIN_ID):
        await callback.answer("⛔ У вас нет прав", show_alert=True)
        return
    
    today = datetime.now()
    start_date = (today + timedelta(days=1)).strftime("%d.%m")
    end_date = (today + timedelta(days=7)).strftime("%d.%m")
    
    bookings = db.get_bookings_by_date_range(start_date, end_date)
    
    if not bookings:
        await callback.message.edit_text(
            "📭 На неделю нет записей",
            reply_markup=get_back_to_admin_keyboard()
        )
        await callback.answer()
        return
    
    # Группируем по датам
    bookings_by_date = {}
    for b in bookings:
        date = b['selected_date']
        if date not in bookings_by_date:
            bookings_by_date[date] = []
        bookings_by_date[date].append(b)
    
    text = f"📅 **Записи на {start_date} - {end_date}:**\n\n"
    
    for date in sorted(bookings_by_date.keys()):
        text += f"**{date}:**\n"
        for b in bookings_by_date[date]:
            status_emoji = "✅" if b['status'] == 'confirmed' else "⏳"
            text += f"  {status_emoji} {b['selected_time']} - {b['full_name']} ({get_booking_type_name(b['booking_type'])})\n"
        text += "\n"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔙 Назад", callback_data="back_to_admin_menu")
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard.as_markup())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_all")
async def admin_all(callback: CallbackQuery):
    """Все записи"""
    if str(callback.from_user.id) != str(ADMIN_ID):
        await callback.answer("⛔ У вас нет прав", show_alert=True)
        return
    
    all_bookings = db.get_all_bookings()
    
    if not all_bookings:
        await callback.message.edit_text(
            "📭 В базе нет записей",
            reply_markup=get_back_to_admin_keyboard()
        )
        await callback.answer()
        return
    
    # Группируем по статусу
    text = "📋 **Все записи:**\n\n"
    
    pending = [b for b in all_bookings if b['status'] == 'pending']
    confirmed = [b for b in all_bookings if b['status'] == 'confirmed']
    rejected = [b for b in all_bookings if b['status'] == 'rejected']
    
    if pending:
        text += "⏳ **Ожидают:**\n"
        for b in pending[:5]:
            text += f"  #{b['id']} {b['selected_date']} {b['selected_time']} - {b['full_name']} ({b['booking_type']})\n"
        text += "\n"
    
    if confirmed:
        text += "✅ **Подтверждены:**\n"
        for b in confirmed[:5]:
            text += f"  #{b['id']} {b['selected_date']} {b['selected_time']} - {b['full_name']}\n"
        text += "\n"
    
    if rejected:
        text += "❌ **Отклонены:**\n"
        for b in rejected[:3]:
            text += f"  #{b['id']} {b['selected_date']} {b['selected_time']} - {b['full_name']}\n"
        text += "\n"
    
    text += f"Всего: {len(all_bookings)} записей"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔙 Назад", callback_data="back_to_admin_menu")
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard.as_markup())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_pending")
async def admin_pending(callback: CallbackQuery):
    """Показать ожидающие записи"""
    if str(callback.from_user.id) != str(ADMIN_ID):
        await callback.answer("⛔ У вас нет прав", show_alert=True)
        return
    
    pending = db.get_pending_bookings()
    
    if not pending:
        await callback.message.edit_text(
            "📭 Нет ожидающих записей",
            reply_markup=get_back_to_admin_keyboard()
        )
        await callback.answer()
        return
    
    text = "⏳ **Ожидающие подтверждения записи:**\n\n"
    for booking in pending:
        text += (
            f"📝 **#{booking['id']}**\n"
            f"👤 {booking['full_name']} (@{booking['username']})\n"
            f"🎯 {get_booking_type_name(booking['booking_type'])}\n"
            f"📅 {booking['selected_date']} {booking['selected_time']}\n"
            f"⏰ Создана: {booking['created_at'][:16]}\n\n"
        )
    
    # Добавляем кнопки для подтверждения/отклонения
    keyboard = InlineKeyboardBuilder()
    for booking in pending[:5]:
        keyboard.button(
            text=f"✅ #{booking['id']}", 
            callback_data=f"confirm_{booking['id']}"
        )
        keyboard.button(
            text=f"❌ #{booking['id']}", 
            callback_data=f"reject_{booking['id']}"
        )
        keyboard.button(
            text=f"🗑 #{booking['id']}", 
            callback_data=f"admin_delete_{booking['id']}"
        )
    
    keyboard.button(text="🔙 Назад", callback_data="back_to_admin_menu")
    keyboard.adjust(3)
    
    await callback.message.edit_text(
        text, 
        parse_mode="Markdown", 
        reply_markup=keyboard.as_markup()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_admin_menu")
async def back_to_admin_menu(callback: CallbackQuery):
    """Возврат в меню админа"""
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="📅 Сегодня", callback_data="admin_today")
    keyboard.button(text="📅 Неделя", callback_data="admin_week")
    keyboard.button(text="📋 Все записи", callback_data="admin_all")
    keyboard.button(text="⏳ Ожидающие", callback_data="admin_pending")
    keyboard.button(text="➕ Ручная запись", callback_data="admin_manual_booking")
    keyboard.button(text="🗑 Удалить запись", callback_data="admin_delete_menu")
    keyboard.adjust(2)
    
    await callback.message.edit_text(
        "📌 **Меню администратора:**\n\n"
        "Выберите действие:",
        parse_mode="Markdown",
        reply_markup=keyboard.as_markup()
    )
    await callback.answer()

# ============= ЗАПУСК =============

async def main():
    logger.info("🚀 Бот запускается...")
    
    # Запускаем планировщик напоминаний в фоне
    asyncio.create_task(check_reminders())
    
    bot_info = await bot.get_me()
    logger.info(f"🤖 Bot: @{bot_info.username}")
    logger.info(f"👤 Admin: {ADMIN_USERNAME} (ID: {ADMIN_ID})")
    logger.info(f"⏰ Планировщик напоминаний запущен")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())