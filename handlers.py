import json
import os
import csv
from aiogram import types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

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
    """Завершает опрос и сохраняет данные"""
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
    user_id = message.from_user.id
    manager = SurveyManager(QUESTIONS)
    active_surveys[user_id] = manager
    await message.answer(QUESTIONS['welcome_message'])
    await state.set_state(SurveyStates.answering)
    await send_next_question(message, manager)

@dp.message(SurveyStates.answering)
async def process_answer(message: types.Message, state: FSMContext):
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
    del active_surveys[user_id]

@dp.message(Command('skip'))
async def cmd_skip(message: types.Message, state: FSMContext):
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
    """Выгружает все заявки в CSV и отправляет файл"""
    
    # Проверка прав
    if str(message.from_user.id) != ADMIN_ID:
        await message.answer("⛔ У вас нет прав для этой команды.")
        return
    
    # Проверяем, есть ли заявки
    leads_count = db.get_recent_leads(1)
    if not leads_count:
        await message.answer("📭 Пока нет ни одной заявки. Нечего выгружать.")
        return
    
    try:
        # Создаём имя файла с датой
        from datetime import datetime
        filename = f"leads_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        # Получаем все заявки
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, user_id, username, full_name, answers, contact_data, created_at
                FROM leads
                ORDER BY created_at DESC
            ''')
            rows = cursor.fetchall()
        
        # Создаём CSV файл
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['ID', 'User ID', 'Username', 'Имя', 'Ответы', 'Контакты', 'Дата'])
            writer.writerows(rows)
        
        # Отправляем файл
        with open(filename, 'rb') as f:
            await message.answer_document(f, caption=f"📎 Все заявки (всего: {len(rows)})")
        
        # Удаляем временный файл
        os.remove(filename)
        
    except Exception as e:
        await message.answer(f"❌ Ошибка при выгрузке: {str(e)}")