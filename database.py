import sqlite3
import json
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
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO leads (user_id, username, full_name, answers, contact_data)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, username, full_name, answers, contact_data))
            conn.commit()
            return cursor.lastrowid
    
    def get_recent_leads(self, limit=5):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, user_id, username, full_name, answers, contact_data, created_at
                FROM leads
                ORDER BY created_at DESC
                LIMIT ?
            ''', (limit,))
            return cursor.fetchall()
    
    def get_stats(self):
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
    
    def get_all_leads(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, user_id, username, full_name, answers, contact_data, created_at
                FROM leads
                ORDER BY created_at DESC
            ''')
            return cursor.fetchall()

db = Database()