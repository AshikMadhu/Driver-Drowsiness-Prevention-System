import time
import numpy as np
from typing import List, Tuple, Dict, Any
from src.utils.logger import logger

class YawnDetector:
    """Calculates Mouth Aspect Ratio (MAR) and monitors yawn duration."""
    
    def __init__(self, mar_threshold: float = 0.50):
        self.mar_threshold = mar_threshold
        self.yawn_start_time = None
        self.is_currently_yawning = False

    def _euclidean_distance(self, pt1: Tuple[int, int], pt2: Tuple[int, int]) -> float:
        """Helper to calculate Euclidean distance between two 2D coordinates."""
        return float(np.sqrt((pt1[0] - pt2[0])**2 + (pt1[1] - pt2[1])**2))

    def calculate_mar(self, mouth_points: List[Tuple[int, int]]) -> float:
        """
        Calculates Mouth Aspect Ratio (MAR) using inner lip landmarks.
        
        Formula: MAR = (||p2 - p8|| + ||p3 - p7|| + ||p4 - p6||) / (3.0 * ||p1 - p5||)
        Indices map: p1=0, p2=1, p3=2, p4=3, p5=4, p6=5, p7=6, p8=7
        """
        if len(mouth_points) < 8:
            return 0.0
            
        try:
            # Vertical distances
            v1 = self._euclidean_distance(mouth_points[1], mouth_points[7])
            v2 = self._euclidean_distance(mouth_points[2], mouth_points[6])
            v3 = self._euclidean_distance(mouth_points[3], mouth_points[5])
            
            # Horizontal distance (corners)
            h = self._euclidean_distance(mouth_points[0], mouth_points[4])
            
            # Avoid division by zero
            if h < 1e-6:
                return 0.0
                
            mar = (v1 + v2 + v3) / (3.0 * h)
            return mar
        except Exception as e:
            logger.error(f"Error calculating MAR: {e}")
            return 0.0

    def process(self, mouth_points: List[Tuple[int, int]]) -> Dict[str, Any]:
        """
        Processes mouth landmarks, updates yawn status, and tracks duration.
        
        Returns:
            Dictionary containing mar, is_yawning, and yawn_duration.
        """
        mar = self.calculate_mar(mouth_points) if mouth_points else 0.0
        
        is_yawning = mar > self.mar_threshold
        yawn_duration = 0.0
        
        if is_yawning:
            if not self.is_currently_yawning or self.yawn_start_time is None:
                self.yawn_start_time = time.time()
                self.is_currently_yawning = True
            yawn_duration = time.time() - self.yawn_start_time
        else:
            self.yawn_start_time = None
            self.is_currently_yawning = False
            
        return {
            "mar": mar,
            "is_yawning": is_yawning,
            "yawn_duration": yawn_duration
        }
