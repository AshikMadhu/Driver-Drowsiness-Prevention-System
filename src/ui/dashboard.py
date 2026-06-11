import streamlit as st
import cv2
import time
import numpy as np
import pandas as pd
from pathlib import Path
from collections import deque
from config import config
import threading
import av
from streamlit_webrtc import webrtc_streamer, WebRtcMode, RTCConfiguration

# Add root folder to python path to resolve imports
import sys
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))

# Core imports
from src.core.camera_manager import CameraManager
from src.cv_engine.face_detector import FaceDetector
from src.cv_engine.landmark_extractor import LandmarkExtractor
from src.cv_engine.eye_detector import EyeDetector
from src.cv_engine.yawn_detector import YawnDetector
from src.cv_engine.head_pose_detector import HeadPoseDetector

# Risk & Persistence
from src.db.database_manager import DatabaseManager
from src.db.event_logger import EventLogger
from src.core.risk_engine import RiskEngine
from src.core.state_manager import StateManager

# Alerts
from src.alert_system.audio_manager import AudioManager
from src.alert_system.voice_alert import VoiceAlert
from src.alert_system.email_service import EmailService
from src.alert_system.notification_service import NotificationService

# Visual Widgets
from src.utils.logger import logger
from src.ui.widgets.cards import render_styled_card, render_risk_card, render_emergency_status_card
from src.ui.analytics.charts import create_realtime_metrics_plot

from src.ml_engine.fatigue_predictor import FatiguePredictor
from src.ml_engine.prediction_service import PredictionService

@st.cache_resource
def get_system_components():
    """Instantiates and caches core system managers to prevent recreation on re-runs."""
    logger_manager = DatabaseManager()
    logger_db = EventLogger(logger_manager)
    state_mgr = StateManager(logger_manager, logger_db)
    
    audio_mgr = AudioManager()
    voice_alert = VoiceAlert()
    email_service = EmailService()
    
    notifier = NotificationService(audio_mgr, voice_alert, email_service, db_manager=logger_manager)
    
    detector = FaceDetector()
    extractor = LandmarkExtractor()
    
    predictor = FatiguePredictor()
    pred_service = PredictionService(logger_manager, predictor)
    
    return {
        "db": logger_manager,
        "event_logger": logger_db,
        "state_manager": state_mgr,
        "audio_manager": audio_mgr,
        "voice_alert": voice_alert,
        "email_service": email_service,
        "notification_service": notifier,
        "face_detector": detector,
        "landmark_extractor": extractor,
        "fatigue_predictor": predictor,
        "prediction_service": pred_service
    }

from typing import Any

def draw_landmark_overlays(frame: cv2.Mat, face_landmarks: Any):
    """Draws a premium, futuristic face mask (contour outline + iris circles) using thin custom styling."""
    import mediapipe as mp
    mp_drawing = mp.solutions.drawing_utils
    mp_face_mesh = mp.solutions.face_mesh

    # Beautiful light neon cyan specs for facial contours
    contour_spec = mp_drawing.DrawingSpec(color=(255, 255, 0), thickness=1, circle_radius=1)
    # Beautiful vibrant neon orange specs for irises
    iris_spec = mp_drawing.DrawingSpec(color=(0, 140, 255), thickness=1, circle_radius=1)

    # Draw Face Outline Contours
    mp_drawing.draw_landmarks(
        image=frame,
        landmark_list=face_landmarks,
        connections=mp_face_mesh.FACEMESH_CONTOURS,
        landmark_drawing_spec=None,
        connection_drawing_spec=contour_spec
    )
    
    # Draw Irises (eye centers)
    if hasattr(face_landmarks, "landmark") and len(face_landmarks.landmark) >= 478:
        mp_drawing.draw_landmarks(
            image=frame,
            landmark_list=face_landmarks,
            connections=mp_face_mesh.FACEMESH_IRISES,
            landmark_drawing_spec=None,
            connection_drawing_spec=iris_spec
        )

class DriverSafetyVideoProcessor(VideoProcessorBase):
    """Asynchronous WebRTC Video Processor for real-time driver telemetry evaluation."""
    def __init__(self, sys_components, ear_th, mar_th, gaze_th):
        self.detector = sys_components["face_detector"]
        self.extractor = sys_components["landmark_extractor"]
        self.state_mgr = sys_components["state_manager"]
        self.notifier = sys_components["notification_service"]
        
        self.eye_dec = EyeDetector(ear_threshold=ear_th)
        self.yawn_dec = YawnDetector(mar_threshold=mar_th)
        self.pose_dec = HeadPoseDetector(deviation_threshold=gaze_th)
        self.risk_engine = RiskEngine(
            window_size=10, 
            head_drop_threshold=-12.0, 
            distraction_threshold=gaze_th
        )
        
        self.lock = threading.Lock()
        
        # Telemetry metrics read by UI thread
        self.last_ear = 0.28
        self.last_mar = 0.12
        self.last_pitch = 0.0
        self.last_yaw = 0.0
        self.last_roll = 0.0
        self.last_score = 0
        self.last_level = "Safe"
        
        # Session parameters set dynamically by UI thread
        self.session_id = None
        self.username = "default_driver"

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        try:
            img = frame.to_ndarray(format="bgr24")
            h, w, _ = img.shape
            
            with self.lock:
                session_id = self.session_id
                username = self.username
                
            # 1. Process facial landmarks
            results = self.detector.process_frame(img)
            
            risk_level = "Safe"
            raw_score = 0
            avg_ear = 0.28
            mar = 0.12
            pitch = 0.0
            yaw = 0.0
            roll = 0.0
            p1, p2 = None, None
            
            if results and results.multi_face_landmarks:
                face_landmarks = results.multi_face_landmarks[0]
                features = self.extractor.extract(face_landmarks, w, h)
                
                if features:
                    # 2. Extract metrics
                    eye_results = self.eye_dec.process(features["left_eye"], features["right_eye"])
                    avg_ear = eye_results["avg_ear"]
                    
                    yawn_results = self.yawn_dec.process(features["mouth"])
                    mar = yawn_results["mar"]
                    
                    pose_results = self.pose_dec.process(features["head_pose_points"], w, h)
                    pitch = pose_results["pitch"]
                    yaw = pose_results["yaw"]
                    roll = pose_results["roll"]
                    p1 = pose_results["nose_tip_center"]
                    p2 = pose_results["nose_projected_tip"]
                    
                    # 3. Process Risk Score & Transitions
                    risk_res = self.risk_engine.process(
                        eye_results["closure_duration"], 
                        yawn_results["yawn_duration"], 
                        pose_results["head_down_duration"], 
                        pose_results["yaw_distraction_duration"]
                    )
                    raw_score = risk_res["raw_score"]
                    
                    # Update DB states
                    risk_level = self.state_mgr.update_risk_state(
                        risk_res, avg_ear, mar, pitch, yaw, roll
                    )
                    
                    # Process notifications
                    self.notifier.process_risk_state(
                        username, risk_level, risk_res["indicators"], 
                        avg_ear, mar, pitch, yaw,
                        frame=img, session_id=session_id
                    )
                    
                    # Render overlays
                    draw_landmark_overlays(img, face_landmarks)
                    if p1 and p2:
                        cv2.line(img, p1, p2, (0, 255, 255), 2)
                        cv2.circle(img, p1, 3, (0, 0, 255), -1)
            else:
                # Normal silent safe state
                self.notifier.process_risk_state(
                    username, "Safe", {"eye_closure": False, "yawn": False, "distraction": False},
                    0.28, 0.12, 0.0, 0.0
                )
                
            # 4. Save telemetry thread-safely
            with self.lock:
                self.last_ear = avg_ear
                self.last_mar = mar
                self.last_pitch = pitch
                self.last_yaw = yaw
                self.last_roll = roll
                self.last_score = raw_score
                self.last_level = risk_level
                
            return av.VideoFrame.from_ndarray(img, format="bgr24")
        except Exception as e:
            logger.error(f"Error in WebRTC video processing thread: {e}")
            return frame

def run_dashboard():
    # Page settings
    st.set_page_config(
        page_title="Intelligent Driver Safety System Dashboard",
        layout="wide",
        page_icon="🛡️"
    )
    
    # Custom CSS for dark theme glassmorphism background
    st.markdown(
        """
        <style>
        .stApp {
            background-color: #0B0C10;
            color: #FFFFFF;
        }
        div[data-testid="stSidebar"] {
            background-color: #12131C;
            border-right: 1px solid #2A2C35;
        }
        .main-header {
            font-family: 'Outfit', 'Inter', sans-serif;
            font-weight: 700;
            background: linear-gradient(90deg, #00F0FF 0%, #FF9E00 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 38px;
            margin-bottom: 2px;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    # Retrieve cached components
    sys_components = get_system_components()
    db = sys_components["db"]
    event_logger = sys_components["event_logger"]
    state_mgr = sys_components["state_manager"]
    notifier = sys_components["notification_service"]
    detector = sys_components["face_detector"]
    extractor = sys_components["landmark_extractor"]
    predictor = sys_components["fatigue_predictor"]
    pred_service = sys_components["prediction_service"]

    # Header section
    st.markdown('<div class="main-header">🛡️ DRIVER SAFETY INTELLIGENCE</div>', unsafe_allow_html=True)
    st.markdown('<div style="color: #8E8E93; font-size: 14px; margin-bottom: 20px;">AI-Powered Drowsiness Prevention & Visual Distraction Tracker</div>', unsafe_allow_html=True)
    
    # Sidebar control panel
    st.sidebar.markdown("### ⚙️ Control & Calibration Panel")
    
    # User Profile
    username = st.sidebar.text_input("Driver Profile Username", value="default_driver")
    
    # Initialize driver profile on demand
    if "driver_initialized" not in st.session_state or st.session_state.get("current_driver") != username:
        state_mgr.initialize_driver(username)
        st.session_state["driver_initialized"] = True
        st.session_state["current_driver"] = username
        
    user_settings = state_mgr.user_settings
    
    # Settings configuration form
    st.sidebar.markdown("#### Alert Thresholds")
    ear_threshold = st.sidebar.slider("Eye Aspect Ratio (EAR) Threshold", 0.15, 0.35, float(user_settings.get("ear_threshold", 0.22)), 0.01)
    mar_threshold = st.sidebar.slider("Mouth Aspect Ratio (MAR) Threshold", 0.30, 0.70, float(user_settings.get("mar_threshold", 0.50)), 0.01)
    gaze_threshold = st.sidebar.slider("Distraction Yaw Angle (Degrees)", 5.0, 30.0, float(user_settings.get("gaze_threshold", 15.0)), 1.0)
    alert_volume = st.sidebar.slider("Alarm Sound Volume", 0.0, 1.0, float(user_settings.get("alert_volume", 0.8)), 0.1)

    # Update settings in SQLite
    if st.sidebar.button("💾 Apply & Save Settings"):
        try:
            with db.connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE settings 
                    SET ear_threshold = ?, mar_threshold = ?, gaze_threshold = ?, alert_volume = ?
                    WHERE user_id = ?;
                    """,
                    (ear_threshold, mar_threshold, gaze_threshold, alert_volume, state_mgr.current_user_id)
                )
            state_mgr.initialize_driver(username) # reload
            sys_components["audio_manager"].set_volume(alert_volume)
            st.sidebar.success("Preferences saved successfully.")
        except Exception as e:
            st.sidebar.error(f"Failed to save preferences: {e}")

    st.sidebar.markdown("---")
    st.sidebar.markdown("#### Session Diagnostics")
    ml_status = "✅ Models Calibrated" if predictor.models_loaded else "⚠️ Calibration Needed"
    st.sidebar.markdown(f"**ML Predictor**: {ml_status}")
    if not predictor.models_loaded:
        st.sidebar.caption("Run 'python train_model.py' to calibrate ML weights.")
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("#### Database Operations")
    if st.sidebar.button("🗑️ Clear Previous Data", width="stretch", disabled=st.session_state.get("active_session", False)):
        if db.clear_database_data():
            st.sidebar.success("All previous session data cleared successfully.")
            if "active_sessions_records" in st.session_state:
                del st.session_state.active_sessions_records
            time.sleep(1.0)
            st.rerun()
        else:
            st.sidebar.error("Failed to clear session data.")
            
    # Initial Session State
    if "active_session" not in st.session_state:
        st.session_state.active_session = False
        st.session_state.session_id = None
        st.session_state.ear_history = deque([0.28] * 100, maxlen=100)
        st.session_state.mar_history = deque([0.15] * 100, maxlen=100)

    # Session Buttons
    col_start, col_stop = st.sidebar.columns(2)
    with col_start:
        if st.button("▶ Start Monitor", width="stretch", disabled=st.session_state.active_session):
            state_mgr.initialize_driver(username)
            session_id = state_mgr.start_session()
            if session_id:
                st.session_state.active_session = True
                st.session_state.session_id = session_id
                st.session_state.start_time = time.time()
                st.session_state.ear_history.clear()
                st.session_state.mar_history.clear()
                st.rerun()
                
    with col_stop:
        if st.button("⏹ Stop Monitor", width="stretch", disabled=not st.session_state.active_session):
            state_mgr.end_session()
            st.session_state.active_session = False
            st.session_state.session_id = None
            notifier.close()
            st.rerun()

    # Main layout division
    col_left, col_right = st.columns([7, 5])

    with col_left:
        # Placeholders for dynamic loop updates
        video_placeholder = st.empty()
        chart_placeholder = st.empty()
        
    with col_right:
        cards_placeholder = st.empty()
        emergency_placeholder = st.empty()
        historical_placeholder = st.empty()

    # --- RUN WEBCAM ACTIVE MONITORING VIA WEBRTC ---
    if st.session_state.active_session:
        # RTC configuration using a public Google STUN server
        RTC_CONFIGURATION = RTCConfiguration(
            {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}
        )
        
        with col_left:
            # We display the WebRTC streamer widget directly inside the left column
            ctx = webrtc_streamer(
                key="driver-safety-streamer",
                mode=WebRtcMode.SENDRECV,
                rtc_configuration=RTC_CONFIGURATION,
                video_processor_factory=lambda: DriverSafetyVideoProcessor(
                    sys_components, ear_threshold, mar_threshold, gaze_threshold
                ),
                media_stream_constraints={"video": True, "audio": False},
                async_processing=True,
            )
        
        if ctx.state.playing:
            # Propagate session details to the background video processor thread
            ctx.video_processor.session_id = st.session_state.session_id
            ctx.video_processor.username = username
            
            try:
                # Non-blocking UI refresh loop that polls processor metrics and updates dashboard widgets
                while ctx.state.playing and st.session_state.active_session:
                    # Thread-safe read of calculated driver safety telemetry
                    with ctx.video_processor.lock:
                        ear = ctx.video_processor.last_ear
                        mar = ctx.video_processor.last_mar
                        score = ctx.video_processor.last_score
                        risk_level = ctx.video_processor.last_level
                    
                    # Update deque history for Plotly visualizations
                    st.session_state.ear_history.append(ear)
                    st.session_state.mar_history.append(mar)
                    
                    # A. Plotly Trend Chart Update
                    fig = create_realtime_metrics_plot(
                        list(st.session_state.ear_history),
                        list(st.session_state.mar_history),
                        ear_threshold,
                        mar_threshold
                    )
                    chart_placeholder.plotly_chart(fig, width="stretch", key=f"trend_chart_{time.time()}")
                    
                    # B. Duration Timer Calculations
                    session_time = time.time() - st.session_state.start_time
                    mins, secs = divmod(int(session_time), 60)
                    duration_str = f"{mins:02d}:{secs:02d}"
                    
                    # C. ML Fatigue Forecast Query
                    pred_res = pred_service.evaluate_session_fatigue(st.session_state.session_id)
                    fatigue_prob = pred_res["fatigue_probability"]
                    pred_label = pred_res["prediction_label"]
                    
                    # D. Render Telemetry Cards
                    with cards_placeholder.container():
                        st.markdown(render_risk_card(risk_level), unsafe_allow_html=True)
                        
                        mc1, mc2, mc3 = st.columns(3)
                        with mc1:
                            st.markdown(render_styled_card("Risk Score", f"{score} / 6", "Maximum: 6"), unsafe_allow_html=True)
                        with mc2:
                            prob_pct = f"{fatigue_prob * 100:.0f}%"
                            theme = "red" if fatigue_prob > 0.5 else "green"
                            st.markdown(render_styled_card("Fatigue Forecast", prob_pct, f"ML Status: {pred_label}", theme), unsafe_allow_html=True)
                        with mc3:
                            st.markdown(render_styled_card("Session Timer", duration_str, "Active Monitoring"), unsafe_allow_html=True)
                            
                    # E. Emergency Email Status Banner
                    emergency_placeholder.markdown(
                        render_emergency_status_card(notifier.emergency_email_dispatched),
                        unsafe_allow_html=True
                    )
                    
                    # Pause before next UI redraw
                    time.sleep(0.3)
                    st.rerun()
                    
            except Exception as e:
                logger.error(f"Dashboard WebRTC UI refresh loop error: {e}")
                st.error(f"UI update thread interrupted: {e}")
            finally:
                notifier.close()
        else:
            video_placeholder.info("📺 Camera stream is offline. Please click 'Start' in the WebRTC stream controller below to begin active monitoring.")
            
    # --- OFFLINE / SUMMARY VIEW DISPLAY ---
    else:
        # Display instruction banner
        video_placeholder.info("📺 Camera Feed Offline. Click 'Start Monitor' in the sidebar to activate the video scanner.")
        # Display historical analysis charts and tables from SQLite
        historical_placeholder.markdown("### 📊 Session Performance Records")
        try:
            with db.connection() as conn:
                df_sessions = pd.read_sql_query(
                    """
                    SELECT s.id as Session_ID, u.username as Driver, s.start_time as Started, s.end_time as Ended,
                           s.total_drowsiness_alerts as Drowsy_Count, s.total_distraction_alerts as Distracted_Count, s.status as Status
                    FROM sessions s
                    JOIN users u ON s.user_id = u.id
                    ORDER BY s.id DESC LIMIT 10;
                    """,
                    conn
                )
                
            if not df_sessions.empty:
                st.session_state.active_sessions_records = df_sessions
                historical_placeholder.dataframe(df_sessions, width="stretch", hide_index=True)
                
                # Add historical summaries
                total_sessions = len(df_sessions)
                total_drowsy = df_sessions["Drowsy_Count"].sum()
                total_distracted = df_sessions["Distracted_Count"].sum()
                
                col_h1, col_h2, col_h3 = chart_placeholder.columns(3)
                with col_h1:
                    st.markdown(render_styled_card("Monitored Sessions", str(total_sessions), "Historical log count"), unsafe_allow_html=True)
                with col_h2:
                    st.markdown(render_styled_card("Cumulative Drowsy Alerts", str(total_drowsy), "EAR alerts logged"), unsafe_allow_html=True)
                with col_h3:
                    st.markdown(render_styled_card("Cumulative Distractions", str(total_distracted), "Gaze deviation alerts"), unsafe_allow_html=True)
            else:
                historical_placeholder.info("No driving sessions recorded in the database yet. Start monitoring to log session data.")
        except Exception as e:
            historical_placeholder.error(f"Failed to load historical summaries: {e}")
            
        # Draw a static information mockup card inside metrics placeholder
        with cards_placeholder.container():
            st.markdown(render_risk_card("Safe"), unsafe_allow_html=True)
            st.markdown(render_styled_card("Safety Score", "100%", "Driver safe"), unsafe_allow_html=True)
            
        emergency_placeholder.markdown(render_emergency_status_card(False), unsafe_allow_html=True)
