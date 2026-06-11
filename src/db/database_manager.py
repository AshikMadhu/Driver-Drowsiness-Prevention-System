import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator
from config import config
from src.utils.logger import logger

class DatabaseManager:
    """Manages SQLite database initialization, schemas, and thread-safe connections."""
    
    def __init__(self, db_path: Path = config.db_path):
        self.db_path = db_path
        # Ensure parent directories exist
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize_database()

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager yielding a thread-safe connection with automatic rollback/commit."""
        conn = sqlite3.connect(self.db_path)
        # Enable foreign key support in SQLite
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database transaction error, rolled back: {e}")
            raise
        finally:
            conn.close()

    def initialize_database(self):
        """Initializes tables and indexes if they do not exist in SQLite."""
        logger.info(f"Initializing SQLite database at: {self.db_path}")
        
        queries = [
            # 1. Users Table
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1
            );
            """,
            # 2. Settings Table
            """
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                ear_threshold REAL DEFAULT 0.22,
                mar_threshold REAL DEFAULT 0.50,
                gaze_threshold REAL DEFAULT 25.0,
                eye_closure_duration_sec REAL DEFAULT 2.0,
                yawn_duration_sec REAL DEFAULT 3.0,
                alert_volume REAL DEFAULT 0.8,
                tts_enabled INTEGER DEFAULT 1,
                alarm_sound_path TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """,
            # 3. Sessions Table
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                end_time TIMESTAMP,
                total_drowsiness_alerts INTEGER DEFAULT 0,
                total_distraction_alerts INTEGER DEFAULT 0,
                status TEXT CHECK(status IN ('ACTIVE', 'COMPLETED', 'ABORTED')) DEFAULT 'ACTIVE',
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """,
            # 4. Events Table
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                event_type TEXT CHECK(event_type IN ('DROWSINESS_WARN', 'DROWSINESS_ALARM', 'YAWN', 'DISTRACTION', 'NORMAL')) NOT NULL,
                confidence_score REAL DEFAULT 1.0,
                ear_value REAL,
                mar_value REAL,
                head_pitch REAL,
                head_yaw REAL,
                head_roll REAL,
                action_taken TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );
            """,
            # Indices
            "CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);",
            "CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);"
        ]
        
        try:
            with self.connection() as conn:
                for query in queries:
                    conn.execute(query)
            logger.info("Database schema verification completed successfully.")
            self._seed_default_user()
        except Exception as e:
            logger.error(f"Critical error initializing database schema: {e}")
            raise

    def clear_database_data(self):
        """Clears all historical driving sessions and event logs from database."""
        logger.info("DatabaseManager: Clearing all driving session data and event logs...")
        try:
            with self.connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM events;")
                cursor.execute("DELETE FROM sessions;")
            logger.info("DatabaseManager: All previous session data successfully cleared.")
            return True
        except Exception as e:
            logger.error(f"DatabaseManager: Failed to clear session data: {e}")
            return False

    def _seed_default_user(self):
        """Creates a default driver profile if the users table is empty."""
        try:
            with self.connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM users;")
                count = cursor.fetchone()[0]
                
                if count == 0:
                    logger.info("Database empty. Seeding default driver user...")
                    cursor.execute("INSERT INTO users (username) VALUES ('default_driver');")
                    user_id = cursor.lastrowid
                    
                    # Seed settings for the default user
                    cursor.execute(
                        """
                        INSERT INTO settings (
                            user_id, ear_threshold, mar_threshold, gaze_threshold,
                            eye_closure_duration_sec, yawn_duration_sec, alert_volume,
                            tts_enabled, alarm_sound_path
                        ) VALUES (?, 0.22, 0.50, 25.0, 2.0, 3.0, 0.8, 1, ?);
                        """,
                        (user_id, str(config.sound_critical_alarm))
                    )
                    logger.info("Default user profile seeded.")
        except Exception as e:
            logger.error(f"Failed to seed default database records: {e}")
            raise
