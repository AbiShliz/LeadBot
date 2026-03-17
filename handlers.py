import json
from aiogram import types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from config import bot, dp, QUESTIONS
from database import db
from survey import SurveyManager, SurveyStates

# Хранилище активных опросников
active_surveys = {}

@dp.message(Command('start'))
async def cmd_start(message: types.Message, state: FSMContext):
    """Начинает опрос"""
    user_id = message.from_user.id
    
    # Создаем новый менеджер опроса
    manager = SurveyManager(QUESTIONS)
    active_surveys[user_id] = manager
    
    # Отправляем приветствие
    await message.answer(QUESTIONS['welcome_message'])
    
    # Переходим к первому вопросу
    await state.set_state(SurveyStates.answering)
    await send_next_question(message, manager)

async def send_next_question(message: types.Message, manager):
    """Отправляет следующий вопрос"""
    question = manager.get_current_question()
    
    if question['type'] == 'text':
        await message.answer(question['text'])
    
    elif question['type'] == 'single_choice':
        # Создаем клавиатуру с вариантами
        kb = types.ReplyKeyboardMarkup(
            keyboard=[[types.KeyboardButton(text=opt['text'])] for opt in question['options']],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await message.answer(question['text'], reply_markup=kb)
    
    elif question['type'] == 'multiple_choice':
        # Для множественного выбора можно сделать инлайн кнопки
        # или простой текстовый ввод с запятыми
        await message.answer(f"{question['text']}\n(можно выбрать несколько через запятую)")

@dp.message(SurveyStates.answering)
async def process_answer(message: types.Message, state: FSMContext):
    """Обрабатывает ответ на вопрос"""
    user_id = message.from_user.id
    manager = active_surveys.get(user_id)
    
    if not manager:
        await message.answer("Ошибка. Начните заново: /start")
        await state.clear()
        return
    
    # Обрабатываем ответ
    result = manager.process_answer(message.text)
    
    if result == 'contact':
        # Переходим к сбору контактов
        if QUESTIONS.get('collect_contact'):
            await state.set_state(SurveyStates.collecting_contact)
            await message.answer(
                "📞 Оставьте ваш контактный телефон\n"
                "(или отправьте /skip если не хотите указывать)",
                reply_markup=types.ReplyKeyboardRemove()
            )
        else:
            # Завершаем опрос
            await finish_survey(message, state, user_id, manager)
    else:
        # Отправляем следующий вопрос
        await send_next_question(message, manager)

@dp.message(SurveyStates.collecting_contact)
async def process_contact(message: types.Message, state: FSMContext):
    """Собирает контактные данные"""
    user_id = message.from_user.id
    manager = active_surveys.get(user_id)
    
    if not manager:
        await message.answer("Ошибка. Начните заново: /start")
        await state.clear()
        return
    
    # Сохраняем контакт
    contact_data = {'phone': message.text}
    
    # Сохраняем в базу
    db.save_lead(
        user_id=user_id,
        username=message.from_user.username or '',
        full_name=message.from_user.full_name,
        answers=manager.format_answers(),
        contact_data=json.dumps(contact_data, ensure_ascii=False)
    )
    
    # Отправляем уведомление менеджеру (если указан)
    if config.ADMIN_ID:
        await bot.send_message(
            config.ADMIN_ID,
            f"🆕 Новая заявка!\n\n"
            f"От: {message.from_user.full_name} (@{message.from_user.username})\n"
            f"Телефон: {message.text}\n\n"
            f"Ответы:\n{manager.format_answers()}"
        )
    
    await message.answer(QUESTIONS['final_message'])
    await state.clear()
    del active_surveys[user_id]

async def finish_survey(message, state, user_id, manager):
    """Завершает опрос без сбора контактов"""
    # Сохраняем без контакта
    db.save_lead(
        user_id=user_id,
        username=message.from_user.username or '',
        full_name=message.from_user.full_name,
        answers=manager.format_answers(),
        contact_data='{}'
    )
    
    await message.answer(QUESTIONS['final_message'])
    await state.clear()
    del active_surveys[user_id]

@dp.message(Command('skip'))
async def cmd_skip(message: types.Message, state: FSMContext):
    """Пропускает текущий шаг"""
    user_id = message.from_user.id
    manager = active_surveys.get(user_id)
    
    if not manager:
        await message.answer("Нет активного опроса. /start")
        await state.clear()
        return
    
    # Если пропускаем контакт
    if await state.get_state() == SurveyStates.collecting_contact:
        await finish_survey(message, state, user_id, manager)
    else:
        await message.answer("Пропустить этот вопрос нельзя")

@dp.message(Command('stats'))
async def cmd_stats(message: types.Message):
    """Статистика для админа"""
    if message.from_user.id != int(config.ADMIN_ID):
        await message.answer("⛔ Доступ запрещён")
        return
    
    stats = db.get_stats()
    text = "📊 <b>Статистика заявок:</b>\n\n"
    for date, count in stats:
        text += f"{date}: {count}\n"
    await message.answer(text)

@dp.message(Command('export'))
async def cmd_export(message: types.Message):
    """Экспорт заявок в CSV"""
    if message.from_user.id != int(config.ADMIN_ID):
        await message.answer("⛔ Доступ запрещён")
        return
    
    filename = db.export_csv()
    with open(filename, 'rb') as f:
        await message.answer_document(f, caption="📎 Заявки в CSV")
