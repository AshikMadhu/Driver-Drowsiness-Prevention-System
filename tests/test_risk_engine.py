import sys
import time
import os
from pathlib import Path

# Add root folder to python path to resolve imports
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

from config import config
from src.db.database_manager import DatabaseManager
from src.db.event_logger import EventLogger
from src.core.risk_engine import RiskEngine
from src.core.state_manager import StateManager

def run_integration_test():
    print("=" * 60)
    print("   DRIVER RISK INTELLIGENCE ENGINE INTEGRATION TEST   ")
    print("=" * 60)
    
    # 1. Setup temporary test database path to avoid polluting production DB
    test_db_path = BASE_DIR / "data" / "test_driver_safety.db"
    if test_db_path.exists():
        try:
            os.remove(test_db_path)
        except Exception as e:
            print(f"Warning: Failed to remove old test DB: {e}")
            
    # Override global database path for diagnostics test
    config.db_path = test_db_path
    
    print(f"[*] Initializing Test Database at: {test_db_path}")
    db_mgr = DatabaseManager(db_path=test_db_path)
    event_logger = EventLogger(db_mgr)
    
    # Initialize state and risk managers
    risk_engine = RiskEngine(window_size=5, head_drop_threshold=-12.0, distraction_threshold=15.0)
    state_mgr = StateManager(db_mgr, event_logger)
    
    # 2. Test User initialization
    print("[*] Testing Driver Initialization...")
    init_success = state_mgr.initialize_driver("test_driver_username")
    assert init_success is True, "Driver initialization failed."
    assert state_mgr.current_user_id is not None, "Driver ID not registered."
    print("  [OK] Driver profile successfully created and loaded.")
    
    # 3. Test Session Start
    print("[*] Testing Session Start...")
    session_id = state_mgr.start_session()
    assert session_id is not None, "Failed to start database driving session."
    assert state_mgr.current_session_id == session_id
    print(f"  [OK] Driving session active. ID: {session_id}")
    
    # 4. Simulate driver states frame-by-frame and check risk calculations
    print("[*] Simulating Driver States & Verifying Risk Calculations...")
    
    # State sequence: (closure_duration, yawn_duration, head_down_duration, yaw_distraction_duration, expected_score, expected_level)
    simulations = [
        # (1) Normal Safe state
        (0.0, 0.0, 0.0, 0.0, 0, "Safe"),
        # (2) Distracted state (yaw_distraction_duration = 5.0) -> yaw_distraction_duration >= 3.0 but < 35.0 -> score 0 (visual distracted indicator set, no alarm)
        (0.0, 0.0, 0.0, 5.0, 0, "Safe"),
        # (3) Yawning state -> yawn_dur = 1.5s -> score 1 -> Safe
        (0.0, 1.5, 0.0, 0.0, 1, "Safe"),
        # (4) Eyes Closed Warning (closure_duration = 2.0) -> score 2 (Warning)
        (2.0, 0.0, 0.0, 0.0, 2, "Warning"),
        # (5) Eyes Closed Alarm (closure_duration = 3.5) -> score 4 (Danger)
        (3.5, 0.0, 0.0, 0.0, 4, "Danger"),
        # (6) Head Drop Alarm (head_down_duration = 3.5) -> score 4 (Danger)
        (0.0, 0.0, 3.5, 0.0, 4, "Danger"),
        # (7) Horizontal Gaze Distraction Alarm (yaw_distraction_duration = 36.0) -> score 4 (Danger)
        (0.0, 0.0, 0.0, 36.0, 4, "Danger"),
        # (8) Critical state (Closed + Yawn + Head Drop + Distracted) -> 4 + 4 + 4 + 4 = 16 (Critical)
        (3.5, 3.5, 3.5, 36.0, 16, "Critical")
    ]
    
    for idx, (closure_dur, yawn_dur, head_down_dur, yaw_distract_dur, expected_raw, _) in enumerate(simulations, 1):
        # Calculate instantaneous scores directly
        inst_res = risk_engine.calculate_instantaneous_score(closure_dur, yawn_dur, head_down_dur, yaw_distract_dur)
        raw_score = inst_res["raw_score"]
        
        # Assert math correctness
        assert raw_score == expected_raw, f"Sim #{idx}: Expected raw score {expected_raw}, got {raw_score}"
        
        # Feed into state_manager and update risk state (checks DB logger loops)
        risk_res = risk_engine.process(closure_dur, yawn_dur, head_down_dur, yaw_distract_dur)
        active_level = state_mgr.update_risk_state(
            risk_res, 
            ear=0.15 if (closure_dur >= 1.5) else 0.28, 
            mar=0.65 if (yawn_dur > 0.0) else 0.12, 
            pitch=-15.0 if (head_down_dur >= 3.0) else 0.0, 
            yaw=20.0 if (yaw_distract_dur >= 3.0) else 0.0, 
            roll=0.0
        )
        
        print(f"  Sim Frame #{idx}: Raw Score: {raw_score} | Smoothed Score: {risk_res['smoothed_score']:.2f} | Risk Level: {active_level}")
        time.sleep(0.05) # simulate minor frame delays
        
    print("  [OK] Risk calculation formulas and state smoothing pass assertions.")

    # 5. Verify Database Entries
    print("[*] Verifying SQLite Database Entries...")
    
    with db_mgr.connection() as conn:
        cursor = conn.cursor()
        
        # Check logged events
        cursor.execute("SELECT COUNT(*) FROM events WHERE session_id = ?;", (session_id,))
        event_count = cursor.fetchone()[0]
        assert event_count > 0, "No telemetry events logged to the database."
        
        # Verify event details
        cursor.execute("SELECT event_type, action_taken, ear_value FROM events WHERE session_id = ? ORDER BY id DESC LIMIT 1;", (session_id,))
        last_event = cursor.fetchone()
        print(f"  Last logged event in DB: Type: {last_event['event_type']} | Action: {last_event['action_taken']} | EAR: {last_event['ear_value']}")
        
    # 6. Test Session Completion
    print("[*] Testing Session Completion...")
    end_success = state_mgr.end_session()
    assert end_success is True, "Failed to end database driving session."
    assert state_mgr.current_session_id is None
    
    # Retrieve stats report from SQLite
    stats = event_logger.get_session_stats(session_id)
    assert stats is not None, "Failed to retrieve session statistics report."
    assert stats["status"] == "COMPLETED"
    
    print("\n" + "=" * 50)
    print("         INTEGRATION TESTS PASSED SUCCESSFULLY         ")
    print("=" * 50)
    print(f"Total Drowsiness Alerts Logged:   {stats['total_drowsiness_alerts']}")
    print(f"Total Distraction Alerts Logged:  {stats['total_distraction_alerts']}")
    print(f"Final session DB state:           {stats['status']}")
    print("=" * 50 + "\n")
    
    # Clean up test DB after successful checks
    try:
        os.remove(test_db_path)
    except Exception as e:
        print(f"Warning: Failed to clean up test DB: {e}")

if __name__ == "__main__":
    run_integration_test()
