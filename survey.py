from aiogram.fsm.state import State, StatesGroup

class SurveyStates(StatesGroup):
    welcome = State()
    answering = State()
    collecting_contact = State()
    finished = State()

class SurveyManager:
    def __init__(self, questions_config):
        self.config = questions_config
        self.questions = {q['id']: q for q in self.config['questions']}
        self.answers = {}
        self.current_question_id = 1  # начинаем с первого вопроса
    
    def get_current_question(self):
        return self.questions.get(self.current_question_id)
    
    def process_answer(self, answer_text, answer_data=None):
        """Сохраняет ответ и возвращает следующий вопрос"""
        # Сохраняем ответ
        self.answers[self.current_question_id] = {
            'text': answer_text,
            'data': answer_data
        }
        
        # Определяем следующий вопрос
        current_q = self.get_current_question()
        next_id = current_q.get('next')
        
        # Если есть ветвление на основе ответа
        if 'options' in current_q and answer_data:
            for opt in current_q['options']:
                if opt.get('text') == answer_text and 'next' in opt:
                    next_id = opt['next']
                    break
        
        self.current_question_id = next_id
        
        # Если следующего вопроса нет — переходим к сбору контактов
        if next_id is None:
            return 'contact'
        
        return self.get_current_question()
    
    def format_answers(self):
        """Форматирует все ответы для вывода"""
        result = []
        for q_id, answer in self.answers.items():
            q = self.questions.get(q_id)
            if q:
                result.append(f"{q['text']}: {answer['text']}")
        return '\n'.join(result)
    
    def is_finished(self):
        return self.current_question_id is None
