import sqlite3
import os

DB_NAME = "database.db"

def create_table():
    if not os.path.exists(DB_NAME):
        print("Database not found.")
        return
    
    conn = sqlite3.connect(DB_NAME)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_id INTEGER,
                content TEXT NOT NULL,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(member_id) REFERENCES members(member_id)
            );
        """)
        conn.commit()
        print("Table 'messages' created successfully.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    create_table()
