import time
from typing import Dict, Any, Optional
from src.alert_system.audio_manager import AudioManager
from src.alert_system.voice_alert import VoiceAlert
from src.alert_system.email_service import EmailService
from src.utils.logger import logger

class NotificationService:
    """Coordinates the multi-level alert feedback framework and emergency escalation logic."""
    
    # Alert levels mapping
    LEVEL_0_NONE = 0      # Driver safe
    LEVEL_1_SOFT_BEEP = 1  # Minor distraction/yawning warning
    LEVEL_2_WARN_ALARM = 2 # Repeated minor warning / moderate fatigue
    LEVEL_3_CONT_ALARM = 3 # Continuous hazard alarm (Danger)
    LEVEL_4_EMERGENCY = 4  # Persistent hazard escalation (Critical)

    def __init__(self, audio_manager: AudioManager, voice_alert: VoiceAlert, email_service: EmailService, db_manager = None):
        self.audio = audio_manager
        self.voice = voice_alert
        self.email = email_service
        
        self.db_mgr = db_manager
            
        # Initialize EvidenceManager for screenshot captures
        try:
            from src.core.evidence_manager import EvidenceManager
            self.evidence = EvidenceManager()
        except Exception as e:
            logger.error(f"NotificationService: Failed to load EvidenceManager: {e}")
            self.evidence = None
            
        # 4th eye closure alarm state tracking
        self.eye_closed_alarm_active = False
        self.eye_closed_alarm_count = 0
        
        self.current_level = self.LEVEL_0_NONE
        
        # State tracking for Level 4 Emergency Escalation
        self.critical_start_time = None
        self.emergency_email_dispatched = False
        
        # TTS Voice warning throttle
        self.last_voice_alert_time = 0.0
        self.voice_alert_cooldown = 8.0 # Seconds before speaking another warning

    def reset(self):
        """Resets the notification service state for a new session."""
        self.eye_closed_alarm_active = False
        self.eye_closed_alarm_count = 0
        self.current_level = self.LEVEL_0_NONE
        self.critical_start_time = None
        self.emergency_email_dispatched = False
        self.last_voice_alert_time = 0.0
        self.audio.stop_all()
        self.voice.stop()
        logger.info("NotificationService: State successfully reset.")

    def process_risk_state(
        self,
        driver_name: str,
        risk_level: str,
        indicators: Dict[str, bool],
        ear: float,
        mar: float,
        pitch: float,
        yaw: float,
        frame = None,
        session_id: Optional[int] = None
    ) -> int:
        """
        Coordinates alarms, speech warnings, and emergency dispatches based on active risk level.
        
        Returns:
            The integer alert level triggered (0 to 4).
        """
        now = time.time()
        
        # Check transition to eye closed alarm (risk_level is Danger or Critical, eye_closure indicator is active)
        is_eye_closed_alarm = indicators.get("eye_closure", False) and (risk_level in ["Danger", "Critical"])
        if is_eye_closed_alarm:
            if not self.eye_closed_alarm_active:
                self.eye_closed_alarm_active = True
                self.eye_closed_alarm_count += 1
                logger.info(f"NotificationService: Eye closed alarm triggered ({self.eye_closed_alarm_count}/4).")
                
                if self.eye_closed_alarm_count == 4:
                    logger.warn("NotificationService: Eye closed alarm triggered for the 4th time! Preparing 4th alarm email report...")
                    self._send_fourth_alarm_email(driver_name, ear, mar, pitch, yaw, frame, session_id)
        else:
            self.eye_closed_alarm_active = False
        
        # Reset and quiet state
        if risk_level == "Safe":
            if self.current_level != self.LEVEL_0_NONE:
                logger.info("NotificationService: Driver recovered to Safe state. Silencing alarms.")
                self.audio.stop_all()
                self.voice.speak("System normal. Drive safely.")
            self.current_level = self.LEVEL_0_NONE
            self.critical_start_time = None
            self.emergency_email_dispatched = False
            return self.current_level

        # --- LEVEL 1 & 2: Warning Alert Level ---
        if risk_level == "Warning":
            self.current_level = self.LEVEL_1_SOFT_BEEP
            self.audio.stop_critical_alarm() # Ensure buzzer is quiet
            self.critical_start_time = None
            
            # Decide warning type
            if indicators.get("distraction"):
                phrase = "Please keep your eyes on the road."
                self.current_level = self.LEVEL_2_WARN_ALARM
            elif indicators.get("yawn"):
                phrase = "Yawning detected. Please consider taking a break."
                self.current_level = self.LEVEL_1_SOFT_BEEP
            elif indicators.get("eye_closure"):
                phrase = "Eyes closing. Wake up."
                self.current_level = self.LEVEL_2_WARN_ALARM
            else:
                phrase = "Caution: Distracted driving patterns detected."
            
            # Play chime once
            self.audio.play_warning_chime()
            
            # Speak warning phrase with throttling
            if now - self.last_voice_alert_time > self.voice_alert_cooldown:
                self.voice.speak(phrase)
                self.last_voice_alert_time = now

        # --- LEVEL 3: Danger Alert Level ---
        elif risk_level == "Danger":
            self.current_level = self.LEVEL_3_CONT_ALARM
            self.critical_start_time = None
            
            # Play continuous loud alarm buzzer
            self.audio.play_critical_alarm()
            
            # Continuous voice alert throttling
            if now - self.last_voice_alert_time > 4.0: # Shorter cooldown for danger
                self.voice.speak("Danger. Drowsiness detected. Wake up immediately.")
                self.last_voice_alert_time = now

        # --- LEVEL 4: Critical Escalation Level ---
        elif risk_level == "Critical":
            self.current_level = self.LEVEL_3_CONT_ALARM # Starts at continuous loop
            self.audio.play_critical_alarm()
            
            # Track persistent critical time
            if self.critical_start_time is None:
                self.critical_start_time = now
                logger.info("NotificationService: Driver entered Critical risk state. Starting escalation timer...")
            
            critical_elapsed = now - self.critical_start_time
            
            # Escalate to Level 4 (Emergency Alert) if critical for > 4.0 seconds
            if critical_elapsed > 4.0:
                self.current_level = self.LEVEL_4_EMERGENCY
                
                # Speak emergency instruction
                if now - self.last_voice_alert_time > 3.0:
                    self.voice.speak("Emergency warning! Pull over immediately! Dispatching alert.")
                    self.last_voice_alert_time = now
                
                # Send emergency email (Only once per event sequence)
                if not self.emergency_email_dispatched:
                    logger.warn("NotificationService: Critical threshold exceeded! Dispatching Level 4 Emergency Email.")
                    
                    screenshot_path = None
                    logger.info(f"NotificationService: Emergency email capture check: frame is not None: {frame is not None}, session_id: {session_id}, self.evidence is not None: {self.evidence is not None}")
                    if frame is not None and session_id is not None and self.evidence is not None:
                        try:
                            screenshot_path = self.evidence.capture_evidence(
                                frame=frame,
                                session_id=session_id,
                                event_type="EMERGENCY_ALARM",
                                ear_value=ear,
                                mar_value=mar,
                                risk_level="Critical",
                                force=True
                            )
                        except Exception as sc_err:
                            logger.error(f"NotificationService: Error capturing emergency screenshot: {sc_err}")
                            
                    details = f"""
                    ALERT STATE TRIGGER METRICS:
                    - EAR Value:       {ear:.3f}
                    - MAR Value:       {mar:.3f}
                    - Head Pitch:      {pitch:.2f} degrees
                    - Head Yaw:        {yaw:.2f} degrees
                    - Critical Duration: {critical_elapsed:.1f} seconds
                    - Active Alarms:   Pygame buzzer + Text-to-speech sirens active
                    """
                    
                    self.email.send_emergency_alert(
                        driver_name=driver_name,
                        risk_level="Critical Emergency",
                        details=details,
                        image_path=str(screenshot_path) if screenshot_path else None
                    )
                    self.emergency_email_dispatched = True

        return self.current_level

    def _send_fourth_alarm_email(self, driver_name: str, ear: float, mar: float, pitch: float, yaw: float, frame, session_id: Optional[int]):
        """Queries database stats, captures a screenshot, and sends details of the 4th repeat alarm."""
        alert_count = 0
        yawn_count = 0
        head_drop_count = 0
        
        if session_id is not None and self.db_mgr is not None:
            try:
                with self.db_mgr.connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM events WHERE session_id = ? AND event_type != 'NORMAL';", (session_id,))
                    alert_count = cursor.fetchone()[0]
                    
                    cursor.execute("SELECT COUNT(*) FROM events WHERE session_id = ? AND event_type = 'YAWN';", (session_id,))
                    yawn_count = cursor.fetchone()[0]
                    
                    cursor.execute("SELECT COUNT(*) FROM events WHERE session_id = ? AND event_type = 'DISTRACTION' AND head_pitch < -12.0;", (session_id,))
                    head_drop_count = cursor.fetchone()[0]
            except Exception as db_err:
                logger.error(f"NotificationService: Error querying 4th alarm stats: {db_err}")
                
        screenshot_path = None
        logger.info(f"NotificationService: 4th alarm email capture check: frame is not None: {frame is not None}, session_id: {session_id}, self.evidence is not None: {self.evidence is not None}")
        if frame is not None and session_id is not None and self.evidence is not None:
            try:
                screenshot_path = self.evidence.capture_evidence(
                    frame=frame,
                    session_id=session_id,
                    event_type="4TH_EYE_CLOSED_ALARM",
                    ear_value=ear,
                    mar_value=mar,
                    risk_level="Critical",
                    force=True
                )
            except Exception as sc_err:
                logger.error(f"NotificationService: Error capturing 4th alarm screenshot: {sc_err}")
                
        details = f"""
        DETAILED REPORT ON 4th EYE CLOSURE ALARM EVENT:
        - Current Session ID:      {session_id if session_id is not None else 'N/A'}
        - Total Session Alerts:    {alert_count}
        - Yawning Event Count:     {yawn_count}
        - Head Drop Event Count:   {head_drop_count}
        
        CURRENT METRICS:
        - EAR:                     {ear:.3f}
        - MAR:                     {mar:.3f}
        - Head Pitch:              {pitch:.2f} degrees
        - Head Yaw:                {yaw:.2f} degrees
        
        Screenshot of safety violation is attached to this email.
        """
        
        subject = f"🚨 4th EYE CLOSURE ALARM: Driver Safety Alert - {driver_name}"
        
        self.email.send_emergency_alert(
            driver_name=driver_name,
            risk_level="Critical Emergency (4th Repeat)",
            details=details,
            image_path=str(screenshot_path) if screenshot_path else None,
            subject=subject,
            receiver="ashiksjc2025@gmail.com"
        )

        return self.current_level

    def close(self):
        """Clean shutdown releases."""
        self.audio.close()
        self.voice.stop()
