import time
import numpy as np
from typing import List, Tuple, Dict, Any
from config import config
from src.utils.logger import logger

class EyeDetector:
    """Calculates Eye Aspect Ratio (EAR) and monitors duration of eye closures."""
    
    def __init__(self, ear_threshold: float = 0.22):
        self.ear_threshold = ear_threshold
        self.closed_start_time = None
        self.is_currently_closed = False
        from collections import deque
        self.ear_history = deque(maxlen=5)

    def _euclidean_distance(self, pt1: Tuple[int, int], pt2: Tuple[int, int]) -> float:
        """Helper to calculate Euclidean distance between two 2D coordinates."""
        return float(np.sqrt((pt1[0] - pt2[0])**2 + (pt1[1] - pt2[1])**2))

    def calculate_ear(self, eye_points: List[Tuple[int, int]]) -> float:
        """
        Calculates Eye Aspect Ratio (EAR) for a single eye.
        
        Formula: EAR = (||p2 - p6|| + ||p3 - p5||) / (2.0 * ||p1 - p4||)
        Indices map: p1=0, p2=1, p3=2, p4=3, p5=4, p6=5
        """
        if len(eye_points) < 6:
            return 0.0
            
        try:
            # Vertical distances
            v1 = self._euclidean_distance(eye_points[1], eye_points[5])
            v2 = self._euclidean_distance(eye_points[2], eye_points[4])
            
            # Horizontal distance
            h = self._euclidean_distance(eye_points[0], eye_points[3])
            
            # Avoid division by zero
            if h < 1e-6:
                return 0.0
                
            ear = (v1 + v2) / (2.0 * h)
            return ear
        except Exception as e:
            logger.error(f"Error calculating EAR: {e}")
            return 0.0

    def process(self, left_eye: List[Tuple[int, int]], right_eye: List[Tuple[int, int]]) -> Dict[str, Any]:
        """
        Processes eye landmarks, updates closure status, and tracks duration.
        
        Returns:
            Dictionary containing left_ear, right_ear, avg_ear, is_closed, and closure_duration.
        """
        ear_left = self.calculate_ear(left_eye) if left_eye else 0.0
        ear_right = self.calculate_ear(right_eye) if right_eye else 0.0
        
        # Calculate average EAR across both eyes
        if left_eye and right_eye:
            avg_ear = (ear_left + ear_right) / 2.0
        elif left_eye:
            avg_ear = ear_left
        elif right_eye:
            avg_ear = ear_right
        else:
            avg_ear = 0.0
            
        if avg_ear > 0.0:
            self.ear_history.append(avg_ear)
        else:
            self.ear_history.clear()
            
        smoothed_ear = sum(self.ear_history) / len(self.ear_history) if self.ear_history else avg_ear
        
        is_closed = smoothed_ear < self.ear_threshold and smoothed_ear > 0.0
        closure_duration = 0.0
        
        if is_closed:
            if not self.is_currently_closed or self.closed_start_time is None:
                self.closed_start_time = time.time()
                self.is_currently_closed = True
            closure_duration = time.time() - self.closed_start_time
        else:
            self.closed_start_time = None
            self.is_currently_closed = False
            
        return {
            "left_ear": ear_left,
            "right_ear": ear_right,
            "avg_ear": smoothed_ear,  # Return smoothed EAR to state manager and logs
            "is_closed": is_closed,
            "closure_duration": closure_duration
        }
