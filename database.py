import sqlite3
import csv
from datetime import datetime

class Database:
    def __init__(self, db_file='quiz.db'):
        self.db_file = db_file
        self.init_db()
    
    def get_connection(self):
        return sqlite3.connect(self.db_file)
    
    def init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    username TEXT,
                    full_name TEXT,
                    answers TEXT,
                    contact_data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
    
    def save_lead(self, user_id, username, full_name, answers, contact_data):
        """Сохраняет заявку"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO leads (user_id, username, full_name, answers, contact_data)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, username, full_name, answers, contact_data))
            conn.commit()
            return cursor.lastrowid
    
    def get_stats(self):
        """Получает статистику заявок"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT DATE(created_at) as date, COUNT(*) as count
                FROM leads
                GROUP BY DATE(created_at)
                ORDER BY date DESC
                LIMIT 10
            ''')
            return cursor.fetchall()
    
    def export_csv(self, filename='leads.csv'):
        """Экспортирует все заявки в CSV"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM leads ORDER BY created_at DESC')
            rows = cursor.fetchall()
            
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['ID', 'User ID', 'Username', 'Name', 'Answers', 'Contact', 'Date'])
                writer.writerows(rows)
            return filename

db = Database()
