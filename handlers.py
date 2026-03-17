import json
import csv
import os
import traceback
from datetime import datetime
from io import BytesIO
from aiogram import types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, FSInputFile

from config import bot, dp, ADMIN_ID, QUESTIONS
from database import db
from survey import SurveyManager

# ==================== СОСТОЯНИЯ FSM ====================

class SurveyStates(StatesGroup):
    answering = State()
    collecting_contact = State()

# ==================== ХРАНИЛИЩЕ АКТИВНЫХ ОПРОСОВ ====================

active_surveys = {}

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

async def send_next_question(message: types.Message, manager):
    """Отправляет следующий вопрос"""
    question = manager.get_current_question()
    
    if question['type'] == 'text':
        await message.answer(question['text'])
    
    elif question['type'] == 'single_choice':
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=opt['text'])] for opt in question['options']],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await message.answer(question['text'], reply_markup=kb)

async def finish_survey(message: types.Message, state: FSMContext, user_id: int, manager):
    """Завершает опрос и сохраняет данные (без контакта)"""
    db.save_lead(
        user_id=user_id,
        username=message.from_user.username or '',
        full_name=message.from_user.full_name,
        answers=manager.format_answers(),
        contact_data='{}'
    )
    
    if ADMIN_ID:
        await bot.send_message(
            ADMIN_ID,
            f"🆕 Новая заявка!\n\n"
            f"От: {message.from_user.full_name} (@{message.from_user.username})\n"
            f"Без контакта\n\n"
            f"Ответы:\n{manager.format_answers()}"
        )
    
    await message.answer(QUESTIONS['final_message'])
    await state.clear()
    if user_id in active_surveys:
        del active_surveys[user_id]

# ==================== ОСНОВНЫЕ КОМАНДЫ ====================

@dp.message(Command('start'))
async def cmd_start(message: types.Message, state: FSMContext):
    """Начинает опрос"""
    user_id = message.from_user.id
    manager = SurveyManager(QUESTIONS)
    active_surveys[user_id] = manager
    await message.answer(QUESTIONS['welcome_message'])
    await state.set_state(SurveyStates.answering)
    await send_next_question(message, manager)

@dp.message(SurveyStates.answering)
async def process_answer(message: types.Message, state: FSMContext):
    """Обрабатывает ответ на вопрос"""
    user_id = message.from_user.id
    manager = active_surveys.get(user_id)
    
    if not manager:
        await message.answer("❌ Ошибка. Начните заново: /start")
        await state.clear()
        return
    
    result = manager.process_answer(message.text)
    
    if result == 'contact':
        if QUESTIONS.get('collect_contact'):
            await state.set_state(SurveyStates.collecting_contact)
            await message.answer(
                "📞 Оставьте ваш контактный телефон\n"
                "(или отправьте /skip если не хотите указывать)",
                reply_markup=ReplyKeyboardRemove()
            )
        else:
            await finish_survey(message, state, user_id, manager)
    else:
        await send_next_question(message, manager)

@dp.message(SurveyStates.collecting_contact)
async def process_contact(message: types.Message, state: FSMContext):
    """Собирает контактные данные"""
    user_id = message.from_user.id
    manager = active_surveys.get(user_id)
    
    if not manager:
        await message.answer("❌ Ошибка. Начните заново: /start")
        await state.clear()
        return
    
    contact_data = {'phone': message.text}
    
    db.save_lead(
        user_id=user_id,
        username=message.from_user.username or '',
        full_name=message.from_user.full_name,
        answers=manager.format_answers(),
        contact_data=json.dumps(contact_data, ensure_ascii=False)
    )
    
    if ADMIN_ID:
        await bot.send_message(
            ADMIN_ID,
            f"🆕 Новая заявка!\n\n"
            f"От: {message.from_user.full_name} (@{message.from_user.username})\n"
            f"Телефон: {message.text}\n\n"
            f"Ответы:\n{manager.format_answers()}"
        )
    
    await message.answer(QUESTIONS['final_message'])
    await state.clear()
    if user_id in active_surveys:
        del active_surveys[user_id]

@dp.message(Command('skip'))
async def cmd_skip(message: types.Message, state: FSMContext):
    """Пропускает текущий шаг (только для контакта)"""
    user_id = message.from_user.id
    manager = active_surveys.get(user_id)
    
    if not manager:
        await message.answer("❌ Нет активного опроса. /start")
        await state.clear()
        return
    
    current_state = await state.get_state()
    if current_state == SurveyStates.collecting_contact.state:
        await finish_survey(message, state, user_id, manager)
    else:
        await message.answer("❌ Пропустить этот вопрос нельзя")

# ==================== АДМИН-КОМАНДЫ ====================

@dp.message(Command('leads'))
async def cmd_leads(message: types.Message):
    """Показать последние 5 заявок (только для админа)"""
    if str(message.from_user.id) != ADMIN_ID:
        await message.answer("⛔ У вас нет прав для этой команды.")
        return
    
    leads = db.get_recent_leads(5)
    
    if not leads:
        await message.answer("📭 Пока нет ни одной заявки.")
        return
    
    text = "📋 <b>Последние 5 заявок:</b>\n\n"
    for lead in leads:
        contact = json.loads(lead[5]) if lead[5] != '{}' else 'не указан'
        if isinstance(contact, dict) and 'phone' in contact:
            contact_display = contact['phone']
        else:
            contact_display = lead[5]
        
        text += f"🆔 <b>ID:</b> {lead[0]}\n"
        text += f"👤 <b>Имя:</b> {lead[3]}\n"
        text += f"📞 <b>Контакт:</b> {contact_display}\n"
        text += f"📅 <b>Дата:</b> {lead[6]}\n"
        text += f"💬 <b>Ответы:</b>\n{lead[4]}\n"
        text += "—\n"
    
    await message.answer(text)

@dp.message(Command('stats'))
async def cmd_stats(message: types.Message):
    """Показать статистику по заявкам (только для админа)"""
    if str(message.from_user.id) != ADMIN_ID:
        await message.answer("⛔ У вас нет прав для этой команды.")
        return
    
    stats = db.get_stats()
    
    if not stats:
        await message.answer("📊 Пока нет статистики.")
        return
    
    text = "📊 <b>Статистика заявок:</b>\n\n"
    for date, count in stats:
        text += f"{date}: {count}\n"
    await message.answer(text)

@dp.message(Command('export'))
async def cmd_export(message: types.Message):
    """Выгружает все заявки в CSV и отправляет файл (исправленная версия)"""
    
    # Проверка прав
    if str(message.from_user.id) != ADMIN_ID:
        await message.answer("⛔ У вас нет прав для этой команды.")
        return

    # Отправляем подтверждение, что процесс начался
    status_msg = await message.answer("⏳ Начинаю подготовку файла...")

    try:
        # Получаем все заявки
        leads = db.get_all_leads()
        
        if not leads:
            await status_msg.edit_text("📭 Пока нет ни одной заявки. Нечего выгружать.")
            return
        
        # Создаём имя файла с датой
        filename = f"leads_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        # Создаём CSV файл
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['ID', 'User ID', 'Username', 'Имя', 'Ответы', 'Контакты', 'Дата'])
            
            for lead in leads:
                contact = lead[5]
                try:
                    contact_dict = json.loads(contact)
                    if isinstance(contact_dict, dict) and 'phone' in contact_dict:
                        contact_display = contact_dict['phone']
                    else:
                        contact_display = str(contact_dict)
                except:
                    contact_display = contact
                
                writer.writerow([
                    lead[0], lead[1], lead[2], lead[3], lead[4], contact_display, lead[6]
                ])
        
        # Проверяем, что файл создан
        if not os.path.exists(filename):
            await status_msg.edit_text("❌ Ошибка: файл не создался")
            return
        
        file_size = os.path.getsize(filename)
        
        # Обновляем статус
        await status_msg.edit_text(
            f"✅ Файл создан (размер: {file_size} байт). Отправляю... ({len(leads)} записей)"
        )
        
        # Пробуем отправить файл разными способами
        send_success = False
        
        # Способ 1: через FSInputFile
        try:
            document = FSInputFile(filename)
            await message.answer_document(
                document,
                caption=f"📎 Все заявки (всего: {len(leads)})"
            )
            send_success = True
            await message.answer("✅ Экспорт завершён успешно!")
            
        except Exception as send_error:
            await message.answer(f"⚠️ Способ 1 не сработал: {str(send_error)}")
            
            # Способ 2: через BytesIO
            try:
                with open(filename, 'rb') as f:
                    file_bytes = f.read()
                file_obj = BytesIO(file_bytes)
                file_obj.name = filename
                await message.answer_document(
                    file_obj,
                    caption=f"📎 Все заявки (всего: {len(leads)}) (способ 2)"
                )
                send_success = True
                await message.answer("✅ Экспорт завершён успешно!")
                
            except Exception as send_error2:
                await message.answer(f"❌ Способ 2 тоже не сработал: {str(send_error2)}")
                
                # Способ 3: пробуем отправить как текст (если файл маленький)
                if file_size < 4096:
                    try:
                        with open(filename, 'r', encoding='utf-8') as f:
                            file_content = f.read()
                        await message.answer(
                            f"📎 Содержимое файла (маленький файл):\n\n{file_content}"
                        )
                        send_success = True
                        await message.answer("✅ Экспорт завершён (как текст)")
                    except Exception as send_error3:
                        await message.answer(f"❌ И способ 3 не сработал: {str(send_error3)}")
        
        # Удаляем временный файл
        os.remove(filename)
        
        if not send_success:
            await message.answer("❌ Не удалось отправить файл ни одним способом.")
        
    except Exception as e:
        error_details = traceback.format_exc()
        error_text = f"❌ Критическая ошибка:\n{str(e)}\n\n{error_details[:500]}"
        print(error_text)  # для логов
        await message.answer(error_text[:1000])

# ==================== АДМИН-ПАНЕЛЬ ====================

@dp.message(Command('admin'))
async def cmd_admin(message: types.Message):
    """Показывает панель администратора с кнопками"""
    if str(message.from_user.id) != ADMIN_ID:
        await message.answer("⛔ У вас нет прав для этой команды.")
        return

    # Создаём клавиатуру с кнопками для админа
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/leads - Последние заявки")],
            [KeyboardButton(text="/stats - Статистика")],
            [KeyboardButton(text="/export - Выгрузить всё")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )

    await message.answer(
        "👮 <b>Панель администратора</b>\n\n"
        "Выберите действие из меню ниже:",
        reply_markup=kb
    )

# ==================== ОБРАБОТКА КНОПОК ====================

@dp.message(F.text.in_(["/leads - Последние заявки", "/stats - Статистика", "/export - Выгрузить всё"]))
async def handle_admin_buttons(message: types.Message):
    """Обрабатывает нажатия на кнопки админ-панели"""
    if str(message.from_user.id) != ADMIN_ID:
        return
    
    if message.text == "/leads - Последние заявки":
        await cmd_leads(message)
    elif message.text == "/stats - Статистика":
        await cmd_stats(message)
    elif message.text == "/export - Выгрузить всё":
        await cmd_export(message)