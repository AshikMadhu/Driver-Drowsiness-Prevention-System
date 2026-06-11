from collections import deque
from typing import Dict, Any, List
from src.utils.logger import logger

class RiskEngine:
    """Calculates driver risk score and determines risk level based on physiological indicators."""
    
    # Risk score mapping
    EYE_CLOSURE_WEIGHT = 2
    YAWN_WEIGHT = 1
    HEAD_DROP_WEIGHT = 2
    DISTRACTION_WEIGHT = 1

    # Risk level names
    LEVEL_SAFE = "Safe"
    LEVEL_WARNING = "Warning"
    LEVEL_DANGER = "Danger"
    LEVEL_CRITICAL = "Critical"

    def __init__(self, window_size: int = 15, head_drop_threshold: float = -12.0, distraction_threshold: float = 15.0):
        self.window_size = window_size
        self.head_drop_threshold = head_drop_threshold
        self.distraction_threshold = distraction_threshold
        
        # Sliding history window to smooth out instantaneous scores
        self.score_history = deque(maxlen=window_size)

    def calculate_instantaneous_score(
        self,
        closure_duration: float,
        yawn_duration: float,
        head_down_duration: float,
        yaw_distraction_duration: float
    ) -> Dict[str, Any]:
        """
        Computes the raw risk score for the current frame.
        
        Rules:
            - Eye Closure: Only alarm (+4) if closed >= 3.0 seconds. 
              Soft Warning (+2) if closed >= 1.5 seconds.
              No alarm/warning for quick blinks (< 1.5 seconds).
            - Yawn: Alarm (+4) if yawned >= 3.0 seconds.
              Soft warning (+1) if yawned > 0.0 seconds.
            - Head Drop (down >= 2.0 seconds) = +4 (Alarm)
            - Yaw Distraction (left/right >= 35.0 seconds) = +4 (Alarm)
              No alarm for mirror check looking to side (< 35 seconds).
        """
        score = 0
        indicators = {
            "eye_closure": False,
            "yawn": False,
            "head_drop": False,
            "distraction": False
        }

        # 1. Eye Closure check (duration-based)
        if closure_duration >= 3.0:
            score += 4 # Triggers Danger/Critical continuous alarm
            indicators["eye_closure"] = True
        elif closure_duration >= 1.5:
            score += 2 # Triggers Warning chime + voice reminder
            indicators["eye_closure"] = True

        # 2. Yawning check (duration-based to ignore talking)
        if yawn_duration >= 3.0:
            score += 4 # Triggers Danger/Critical continuous alarm
            indicators["yawn"] = True
        elif yawn_duration >= 1.5:
            score += 1 # Soft warning (ignored if talking, which has shorter duration)
            indicators["yawn"] = True

        # 3. Head Drop check
        if head_down_duration >= 3.0:
            score += 4 # Triggers Danger/Critical continuous alarm
            indicators["head_drop"] = True
        elif head_down_duration >= 1.5:
            score += 2 # Triggers Warning chime + voice reminder
            indicators["head_drop"] = True

        # 4. Horizontal gaze distraction check
        if yaw_distraction_duration >= 35.0:
            score += 4 # Triggers Danger/Critical continuous alarm
            indicators["distraction"] = True
        elif yaw_distraction_duration >= 3.0:
            # Mark visually as distracted on dashboard, but add 0 to score (no audible alert chime/alarm)
            indicators["distraction"] = True

        return {
            "raw_score": score,
            "indicators": indicators
        }

    def get_risk_level(self, score: float) -> str:
        """Maps a risk score value to safety levels."""
        if score <= 1.5:  # Floats allowed due to smoothing
            return self.LEVEL_SAFE
        elif score <= 3.5:
            return self.LEVEL_WARNING
        elif score <= 5.5:
            return self.LEVEL_DANGER
        else:
            return self.LEVEL_CRITICAL

    def process(
        self,
        closure_duration: float,
        yawn_duration: float,
        head_down_duration: float,
        yaw_distraction_duration: float
    ) -> Dict[str, Any]:
        """
        Evaluates current metrics, updates history, and returns smoothed risk state.
        
        Returns:
            Dictionary containing raw_score, smoothed_score, risk_level, and active indicators.
        """
        result = self.calculate_instantaneous_score(
            closure_duration, yawn_duration, head_down_duration, yaw_distraction_duration
        )
        raw_score = result["raw_score"]
        
        # Append to temporal sliding window
        self.score_history.append(raw_score)
        
        # Calculate moving average
        smoothed_score = sum(self.score_history) / len(self.score_history)
        risk_level = self.get_risk_level(smoothed_score)
        
        return {
            "raw_score": raw_score,
            "smoothed_score": smoothed_score,
            "risk_level": risk_level,
            "indicators": result["indicators"],
            "score_history": list(self.score_history)
        }

    def reset(self):
        """Clears score history."""
        self.score_history.clear()
        logger.info("RiskEngine score history reset.")
