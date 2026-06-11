import cv2
import numpy as np
from typing import List, Tuple, Dict, Any, Optional
from src.utils.logger import logger

class HeadPoseDetector:
    """Estimates head pose (Pitch, Yaw, Roll) using OpenCV solvePnP and a generic 3D face model."""
    
    def __init__(self, deviation_threshold: float = 15.0):
        self.deviation_threshold = deviation_threshold
        # State tracking for duration timers
        self.yaw_distracted_start_time = None
        self.head_down_start_time = None
        from collections import deque
        self.pitch_history = deque(maxlen=5)
        self.yaw_history = deque(maxlen=5)
        
        # Define standard 3D coordinates for the 6 key facial landmarks (in millimeters)
        # 1. Nose Tip (index 0) -> Origin (0, 0, 0)
        # 2. Chin (index 1) -> (0, -330, -65)
        # 3. Left Eye Outer Corner (index 2) -> (225, 170, -135) [Viewer's Right, Face's Left]
        # 4. Right Eye Outer Corner (index 3) -> (-225, 170, -135) [Viewer's Left, Face's Right]
        # 5. Left Mouth Corner (index 4) -> (150, -150, -125)
        # 6. Right Mouth Corner (index 5) -> (-150, -150, -125)
        self.model_points = np.array([
            (0.0, 0.0, 0.0),             # Nose tip
            (0.0, 330.0, 65.0),          # Chin
            (225.0, -170.0, 135.0),      # Left Eye Outer Corner
            (-225.0, -170.0, 135.0),     # Right Eye Outer Corner
            (150.0, 150.0, 125.0),       # Left Mouth Corner
            (-150.0, 150.0, 125.0)       # Right Mouth Corner
        ], dtype=np.float32)

    def estimate_pose(self, head_pose_points: List[Tuple[int, int]], img_width: int, img_height: int) -> Optional[Dict[str, Any]]:
        """
        Calculates rotation and translation vectors using PNP solver and extracts Euler angles.
        
        Args:
            head_pose_points: List of 6 2D coordinate tuples corresponding to model_points.
            img_width: Width of the camera frame
            img_height: Height of the camera frame
            
        Returns:
            Dictionary with pitch, yaw, roll (degrees), nose_end_point2D (for drawing line), or None if error.
        """
        if len(head_pose_points) < 6:
            return None
            
        try:
            # Format image points as a numpy float array
            image_points = np.array(head_pose_points, dtype=np.float32)
            
            # Approximate camera intrinsic matrix based on focal length (matching frame width)
            focal_length = img_width
            center = (img_width / 2.0, img_height / 2.0)
            camera_matrix = np.array([
                [focal_length, 0.0, center[0]],
                [0.0, focal_length, center[1]],
                [0.0, 0.0, 1.0]
            ], dtype=np.float32)
            
            # Assume no lens distortion
            dist_coeffs = np.zeros((4, 1), dtype=np.float32)
            
            # Solve Perspective-n-Point (PnP) problem
            success, rvec, tvec = cv2.solvePnP(
                self.model_points, 
                image_points, 
                camera_matrix, 
                dist_coeffs, 
                flags=cv2.SOLVEPNP_ITERATIVE
            )
            
            if not success:
                return None
                
            # Convert rotation vector to 3x3 rotation matrix
            R, _ = cv2.Rodrigues(rvec)
            
            # Deconstruct rotation matrix R to Euler angles (Pitch, Yaw, Roll)
            sy = np.sqrt(R[0, 0] * R[0, 0] + R[1, 0] * R[1, 0])
            singular = sy < 1e-6
            
            if not singular:
                x = np.arctan2(R[2, 1], R[2, 2]) # Pitch
                y = np.arctan2(-R[2, 0], sy)     # Yaw
                z = np.arctan2(R[1, 0], R[0, 0]) # Roll
            else:
                x = np.arctan2(-R[1, 2], R[1, 1])
                y = np.arctan2(-R[2, 0], sy)
                z = 0.0
                
            # Convert radians to degrees
            pitch = x * 180.0 / np.pi
            yaw = y * 180.0 / np.pi
            roll = z * 180.0 / np.pi
            
            is_mirrored = False
            # Check if the result is flipped (upside down / rolled 180 degrees)
            if abs(pitch) > 90.0 or abs(roll) > 90.0:
                is_mirrored = True
                # The coordinates are likely mirrored. Let's flip the X-coordinates and solve again!
                image_points_mirrored = image_points.copy()
                image_points_mirrored[:, 0] = img_width - image_points_mirrored[:, 0]
                
                success, rvec, tvec = cv2.solvePnP(
                    self.model_points, 
                    image_points_mirrored, 
                    camera_matrix, 
                    dist_coeffs, 
                    flags=cv2.SOLVEPNP_ITERATIVE
                )
                if success:
                    R, _ = cv2.Rodrigues(rvec)
                    sy = np.sqrt(R[0, 0] * R[0, 0] + R[1, 0] * R[1, 0])
                    singular = sy < 1e-6
                    if not singular:
                        x = np.arctan2(R[2, 1], R[2, 2])
                        y = np.arctan2(-R[2, 0], sy)
                        z = np.arctan2(R[1, 0], R[0, 0])
                    else:
                        x = np.arctan2(-R[1, 2], R[1, 1])
                        y = np.arctan2(-R[2, 0], sy)
                        z = 0.0
                    pitch = x * 180.0 / np.pi
                    yaw = y * 180.0 / np.pi
                    roll = z * 180.0 / np.pi
            
            # Project a 3D point (250mm out from the nose tip) onto the 2D plane to draw a direction vector
            nose_end_point3D = np.array([(0.0, 0.0, 250.0)], dtype=np.float32)
            (nose_end_point2D, _) = cv2.projectPoints(
                nose_end_point3D, 
                rvec, 
                tvec, 
                camera_matrix, 
                dist_coeffs
            )
            
            # Convert projected coordinate to integer coordinate tuple
            p1 = (int(head_pose_points[0][0]), int(head_pose_points[0][1])) # Original nose tip in image space
            p2_x = int(nose_end_point2D[0][0][0])
            p2_y = int(nose_end_point2D[0][0][1])
            
            if is_mirrored:
                # Mirror the projected X coordinate back so it aligns with the mirrored frame display
                p2_x = int(img_width - p2_x)
                
            p2 = (p2_x, p2_y)
            
            # Smooth pitch and yaw using rolling averages
            self.pitch_history.append(pitch)
            self.yaw_history.append(yaw)
            
            smoothed_pitch = sum(self.pitch_history) / len(self.pitch_history)
            smoothed_yaw = sum(self.yaw_history) / len(self.yaw_history)
            
            # Check deviation (distraction)
            # Use smoothed yaw for distraction checks
            is_yaw_distracted = abs(smoothed_yaw) > self.deviation_threshold
            is_head_down = smoothed_pitch < -12.0 # Head dropped down (standard threshold)
            is_distracted = is_yaw_distracted or abs(smoothed_pitch) > self.deviation_threshold
            
            import time
            # State-based yaw distraction timer
            if is_yaw_distracted:
                if self.yaw_distracted_start_time is None:
                    self.yaw_distracted_start_time = time.time()
                yaw_distraction_duration = time.time() - self.yaw_distracted_start_time
            else:
                self.yaw_distracted_start_time = None
                yaw_distraction_duration = 0.0
                
            # State-based head down timer
            if is_head_down:
                if self.head_down_start_time is None:
                    self.head_down_start_time = time.time()
                head_down_duration = time.time() - self.head_down_start_time
            else:
                self.head_down_start_time = None
                head_down_duration = 0.0
                              
            return {
                "pitch": smoothed_pitch,
                "yaw": smoothed_yaw,
                "roll": roll,
                "nose_tip_center": p1,
                "nose_projected_tip": p2,
                "is_distracted": is_distracted,
                "yaw_distraction_duration": yaw_distraction_duration,
                "head_down_duration": head_down_duration
            }
            
        except Exception as e:
            logger.error(f"Error estimating head pose: {e}")
            return None
            
    def process(self, head_pose_points: List[Tuple[int, int]], img_width: int, img_height: int) -> Dict[str, Any]:
        """
        Public process wrapper returning a safe default dictionary if estimation fails.
        """
        result = self.estimate_pose(head_pose_points, img_width, img_height)
        if result is None:
            self.pitch_history.clear()
            self.yaw_history.clear()
            return {
                "pitch": 0.0,
                "yaw": 0.0,
                "roll": 0.0,
                "nose_tip_center": None,
                "nose_projected_tip": None,
                "is_distracted": False,
                "yaw_distraction_duration": 0.0,
                "head_down_duration": 0.0
            }
        return result
