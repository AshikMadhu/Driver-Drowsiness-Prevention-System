import time
from typing import Dict, Any, Optional
from src.db.database_manager import DatabaseManager
from src.db.event_logger import EventLogger
from src.utils.logger import logger

class StateManager:
    """Manages active driver session, settings, state transitions, and throttled database logging."""
    
    def __init__(self, db_manager: DatabaseManager, event_logger: EventLogger):
        self.db = db_manager
        self.event_logger = event_logger
        
        self.current_user_id: Optional[int] = None
        self.current_username: Optional[str] = None
        self.current_session_id: Optional[int] = None
        
        self.current_risk_level = "Safe"
        self.user_settings: Dict[str, Any] = {}
        
        # Throttling database logging to avoid locking SQLite with thousands of writes
        self.last_log_timestamps: Dict[str, float] = {
            "DROWSINESS_WARN": 0.0,
            "DROWSINESS_ALARM": 0.0,
            "YAWN": 0.0,
            "DISTRACTION": 0.0,
            "NORMAL": 0.0
        }
        self.log_cooldown_seconds = 2.0 # Minimum gap between consecutive database log entries of same type

    def initialize_driver(self, username: str = "default_driver") -> bool:
        """
        Looks up user details in the database or creates a new user if missing.
        Loads driver settings.
        """
        try:
            with self.db.connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM users WHERE username = ? AND is_active = 1;", (username,))
                row = cursor.fetchone()
                
                if row:
                    self.current_user_id = row["id"]
                else:
                    logger.info(f"Driver '{username}' not found. Registering profile...")
                    cursor.execute("INSERT INTO users (username) VALUES (?);", (username,))
                    self.current_user_id = cursor.lastrowid
                    
                    # Copy default settings
                    cursor.execute(
                        """
                        INSERT INTO settings (
                            user_id, ear_threshold, mar_threshold, gaze_threshold,
                            eye_closure_duration_sec, yawn_duration_sec, alert_volume,
                            tts_enabled, alarm_sound_path
                        ) VALUES (?, 0.22, 0.50, 25.0, 2.0, 3.0, 0.8, 1, 'data/audio/critical_alarm.wav');
                        """,
                        (self.current_user_id,)
                    )
                
                self.current_username = username
                self._load_user_settings(cursor)
                return True
        except Exception as e:
            logger.error(f"StateManager: Failed to initialize driver: {e}")
            return False

    def _load_user_settings(self, cursor: Any):
        """Loads thresholds and preferences for the current user into memory."""
        cursor.execute(
            """
            SELECT ear_threshold, mar_threshold, gaze_threshold,
                   eye_closure_duration_sec, yawn_duration_sec,
                   alert_volume, tts_enabled, alarm_sound_path
            FROM settings WHERE user_id = ?;
            """,
            (self.current_user_id,)
        )
        row = cursor.fetchone()
        if row:
            self.user_settings = dict(row)
            logger.info(f"StateManager: Driver preferences successfully loaded: {self.user_settings}")

    def start_session(self) -> Optional[int]:
        """Starts a new driving session under the active driver profile."""
        if not self.current_user_id:
            logger.error("StateManager: Cannot start session. Driver profile not initialized.")
            return None
            
        self.current_session_id = self.event_logger.start_session(self.current_user_id)
        self.current_risk_level = "Safe"
        return self.current_session_id

    def end_session(self) -> bool:
        """Ends the active driving session."""
        if not self.current_session_id:
            return False
            
        success = self.event_logger.end_session(self.current_session_id, "COMPLETED")
        self.current_session_id = None
        self.current_risk_level = "Safe"
        return success

    def update_risk_state(
        self,
        risk_evaluation: Dict[str, Any],
        ear: float,
        mar: float,
        pitch: float,
        yaw: float,
        roll: float
    ) -> str:
        """
        Takes CV metrics and risk engine output, coordinates database logs, and checks state transitions.
        
        Returns:
            The current active risk level.
        """
        if not self.current_session_id:
            return "Safe"
            
        new_risk_level = risk_evaluation["risk_level"]
        indicators = risk_evaluation["indicators"]
        now = time.time()
        
        # Transition tracking
        if new_risk_level != self.current_risk_level:
            logger.info(f"StateManager: Risk state transition: {self.current_risk_level} -> {new_risk_level}")
            self.current_risk_level = new_risk_level

        # Database Logging with Cooldown Throttling
        # Check active indicators and log events if cooldown expired
        if indicators["eye_closure"]:
            # Check duration - distinguish warning vs alarm
            is_alarm = risk_evaluation["raw_score"] >= 4  # Danger / Critical trigger
            event_type = "DROWSINESS_ALARM" if is_alarm else "DROWSINESS_WARN"
            
            if now - self.last_log_timestamps[event_type] > self.log_cooldown_seconds:
                self.event_logger.log_event(
                    self.current_session_id, event_type, ear, mar, pitch, yaw, roll,
                    action_taken="LOGGED"
                )
                self.last_log_timestamps[event_type] = now
                
        elif indicators["yawn"]:
            if now - self.last_log_timestamps["YAWN"] > self.log_cooldown_seconds:
                self.event_logger.log_event(
                    self.current_session_id, "YAWN", ear, mar, pitch, yaw, roll,
                    action_taken="LOGGED"
                )
                self.last_log_timestamps["YAWN"] = now
                
        elif indicators["distraction"] or indicators["head_drop"]:
            if now - self.last_log_timestamps["DISTRACTION"] > self.log_cooldown_seconds:
                self.event_logger.log_event(
                    self.current_session_id, "DISTRACTION", ear, mar, pitch, yaw, roll,
                    action_taken="LOGGED"
                )
                self.last_log_timestamps["DISTRACTION"] = now
                
        else:
            # Periodic logging of NORMAL state (e.g. every 10 seconds to keep telemetry timeline)
            if now - self.last_log_timestamps["NORMAL"] > 10.0:
                self.event_logger.log_event(
                    self.current_session_id, "NORMAL", ear, mar, pitch, yaw, roll,
                    action_taken="TELEMETRY"
                )
                self.last_log_timestamps["NORMAL"] = now

        return self.current_risk_level
