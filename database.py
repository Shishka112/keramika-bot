import sqlite3
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

class Database:
    def __init__(self, db_name="bookings.db"):
        self.db_name = db_name
        self.init_db()
    
    def init_db(self):
        """Инициализация таблиц"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            
            # Таблица для заявок на запись
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bookings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    full_name TEXT,
                    booking_type TEXT NOT NULL,
                    selected_date TEXT,
                    selected_time TEXT,
                    status TEXT DEFAULT 'pending',
                    admin_message_id INTEGER,
                    reminder_day_sent INTEGER DEFAULT 0,
                    reminder_hour_sent INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Добавляем новые столбцы, если их нет (для старых баз)
            try:
                cursor.execute('ALTER TABLE bookings ADD COLUMN reminder_day_sent INTEGER DEFAULT 0')
            except:
                pass
            try:
                cursor.execute('ALTER TABLE bookings ADD COLUMN reminder_hour_sent INTEGER DEFAULT 0')
            except:
                pass
            
            conn.commit()
    
    def create_booking(self, user_id: int, username: str, full_name: str, 
                      booking_type: str, date: str, time: str) -> int:
        """Создание новой заявки на запись"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO bookings 
                (user_id, username, full_name, booking_type, selected_date, selected_time, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, username, full_name, booking_type, date, time, 'pending'))
            conn.commit()
            return cursor.lastrowid
    
    def get_pending_bookings(self) -> List[Dict[str, Any]]:
        """Получение всех неподтвержденных заявок"""
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM bookings 
                WHERE status = 'pending' 
                ORDER BY created_at DESC
            ''')
            return [dict(row) for row in cursor.fetchall()]
    
    def get_confirmed_bookings(self) -> List[Dict[str, Any]]:
        """Получение всех подтвержденных заявок"""
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM bookings 
                WHERE status = 'confirmed' 
                ORDER BY selected_date ASC, selected_time ASC
            ''')
            return [dict(row) for row in cursor.fetchall()]
    
    def get_all_bookings(self) -> List[Dict[str, Any]]:
        """Получение всех заявок (для админа)"""
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM bookings 
                ORDER BY 
                    CASE status
                        WHEN 'pending' THEN 1
                        WHEN 'confirmed' THEN 2
                        WHEN 'rejected' THEN 3
                        ELSE 4
                    END,
                    created_at DESC
            ''')
            return [dict(row) for row in cursor.fetchall()]
    
    def get_bookings_by_date_range(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """Получение заявок за определенный период"""
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM bookings 
                WHERE selected_date BETWEEN ? AND ?
                AND status IN ('pending', 'confirmed')
                ORDER BY selected_date ASC, selected_time ASC
            ''', (start_date, end_date))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_booked_slots(self, date: str) -> List[str]:
        """Получение занятых временных слотов на конкретную дату"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT selected_time FROM bookings 
                WHERE selected_date = ? 
                AND status IN ('pending', 'confirmed')
            ''', (date,))
            return [row[0] for row in cursor.fetchall()]
    
    def is_slot_available(self, date: str, time: str) -> bool:
        """Проверка, свободен ли слот"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) FROM bookings 
                WHERE selected_date = ? AND selected_time = ? 
                AND status IN ('pending', 'confirmed')
            ''', (date, time))
            count = cursor.fetchone()[0]
            return count == 0
    
    def get_booking(self, booking_id: int) -> Optional[Dict[str, Any]]:
        """Получение заявки по ID"""
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM bookings WHERE id = ?', (booking_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def update_booking_status(self, booking_id: int, status: str, admin_message_id: int = None):
        """Обновление статуса заявки"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            if admin_message_id:
                cursor.execute('''
                    UPDATE bookings 
                    SET status = ?, admin_message_id = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (status, admin_message_id, booking_id))
            else:
                cursor.execute('''
                    UPDATE bookings 
                    SET status = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (status, booking_id))
            conn.commit()
    
    def delete_booking(self, booking_id: int) -> bool:
        """Удаление записи"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM bookings WHERE id = ?', (booking_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    def get_user_bookings(self, user_id: int) -> List[Dict[str, Any]]:
        """Получение всех записей пользователя"""
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM bookings 
                WHERE user_id = ? 
                ORDER BY created_at DESC
            ''', (user_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_bookings_summary(self) -> Dict[str, int]:
        """Получение сводки по записям"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT status, COUNT(*) FROM bookings 
                GROUP BY status
            ''')
            summary = dict(cursor.fetchall())
            return {
                'pending': summary.get('pending', 0),
                'confirmed': summary.get('confirmed', 0),
                'rejected': summary.get('rejected', 0),
                'total': sum(summary.values())
            }
    
    def mark_reminder_sent(self, booking_id: int, reminder_type: str):
        """Отметить, что напоминание отправлено"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            if reminder_type == 'day':
                cursor.execute('UPDATE bookings SET reminder_day_sent = 1 WHERE id = ?', (booking_id,))
            elif reminder_type == 'hour':
                cursor.execute('UPDATE bookings SET reminder_hour_sent = 1 WHERE id = ?', (booking_id,))
            conn.commit()

# Создаем экземпляр базы данных для импорта
db = Database()