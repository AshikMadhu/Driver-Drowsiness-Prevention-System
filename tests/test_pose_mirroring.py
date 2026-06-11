import sys
import unittest
import numpy as np
import cv2
from pathlib import Path

# Align paths
sys.path.append(str(Path(__file__).parent.parent.absolute()))

from src.cv_engine.head_pose_detector import HeadPoseDetector

class TestPoseMirroring(unittest.TestCase):
    
    def setUp(self):
        self.detector = HeadPoseDetector(deviation_threshold=15.0)
        
    def project_model_points(self, yaw_deg: float, pitch_deg: float = 0.0, roll_deg: float = 0.0, mirrored: bool = False):
        """Simulates 2D image coordinates by projecting the 3D model under rotations."""
        r_yaw = np.radians(yaw_deg)
        r_pitch = np.radians(pitch_deg)
        r_roll = np.radians(roll_deg)
        
        # Rotation matrices
        R_y = np.array([
            [np.cos(r_yaw), 0, np.sin(r_yaw)],
            [0, 1, 0],
            [-np.sin(r_yaw), 0, np.cos(r_yaw)]
        ])
        R_x = np.array([
            [1, 0, 0],
            [0, np.cos(r_pitch), -np.sin(r_pitch)],
            [0, np.sin(r_pitch), np.cos(r_pitch)]
        ])
        R_z = np.array([
            [np.cos(r_roll), -np.sin(r_roll), 0],
            [np.sin(r_roll), np.cos(r_roll), 0],
            [0, 0, 1]
        ])
        R = R_z @ R_y @ R_x
        
        # Rotate model points
        pts_rotated = (R @ self.detector.model_points.T).T
        
        # Project to 2D image coordinates (camera focal length matching width, center at 320x240)
        img_width, img_height = 640, 480
        focal_length = img_width
        cx, cy = img_width / 2.0, img_height / 2.0
        
        projected_pts = []
        for pt in pts_rotated:
            x, y, z = pt[0], pt[1], pt[2] + 600.0 # Place 600mm away
            px = (x * focal_length / z) + cx
            py = (y * focal_length / z) + cy
            if mirrored:
                px = img_width - px
            projected_pts.append((int(px), int(py)))
        return projected_pts

    def test_non_mirrored_symmetry(self):
        """Verifies that non-mirrored inputs produce correct symmetric yaw values."""
        # 1. Look right (negative yaw in standard rotation)
        pts_right = self.project_model_points(yaw_deg=-20.0)
        res_right = self.detector.process(pts_right, 640, 480)
        
        # 2. Look left (positive yaw in standard rotation)
        pts_left = self.project_model_points(yaw_deg=20.0)
        res_left = self.detector.process(pts_left, 640, 480)
        
        # Verify pitches are close to 0 (not flipped)
        self.assertLess(abs(res_right["pitch"]), 10.0)
        self.assertLess(abs(res_left["pitch"]), 10.0)
        
        # Verify yaws are symmetric
        self.assertLess(res_right["yaw"], -10.0)
        self.assertGreater(res_left["yaw"], 10.0)
        self.assertAlmostEqual(abs(res_right["yaw"]), abs(res_left["yaw"]), delta=3.0)

    def test_mirrored_self_healing(self):
        """Verifies that mirrored inputs are detected and corrected, yielding correct yaw and pitch."""
        # 1. Look right in real life -> mirrored left in image
        pts_right_mir = self.project_model_points(yaw_deg=-20.0, mirrored=True)
        res_right_mir = self.detector.process(pts_right_mir, 640, 480)
        
        # 2. Look left in real life -> mirrored right in image
        pts_left_mir = self.project_model_points(yaw_deg=20.0, mirrored=True)
        res_left_mir = self.detector.process(pts_left_mir, 640, 480)
        
        # Verify self-healing corrected the pitch (otherwise it would be ~ -180.0)
        self.assertLess(abs(res_right_mir["pitch"]), 10.0)
        self.assertLess(abs(res_left_mir["pitch"]), 10.0)
        
        # Verify yaws are correct and symmetric in mirrored space
        self.assertLess(res_right_mir["yaw"], -10.0)
        self.assertGreater(res_left_mir["yaw"], 10.0)
        self.assertAlmostEqual(abs(res_right_mir["yaw"]), abs(res_left_mir["yaw"]), delta=3.0)

        # Verify that nose projected vector tip is mirrored back correctly for visualization
        # Nose tip center (p1) is around (320, 240)
        # For looking left (yaw > 0), the unmirrored nose points to viewer's right (larger x).
        # In mirrored mode, when driver looks left, they face viewer's left (smaller x).
        # So res_left_mir["nose_projected_tip"][0] should be less than the nose center (320).
        p1 = res_left_mir["nose_tip_center"]
        p2 = res_left_mir["nose_projected_tip"]
        self.assertLess(p2[0], p1[0])

if __name__ == "__main__":
    unittest.main()
