import os
import sys
import subprocess
import argparse
import importlib.util
from pathlib import Path

# ANSI colors for presentation-ready terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def log_success(msg):
    print(f"{Colors.OKGREEN}[OK] {msg}{Colors.ENDC}")

def log_warning(msg):
    print(f"{Colors.WARNING}[WARN] {msg}{Colors.ENDC}")

def log_fail(msg):
    print(f"{Colors.FAIL}[FAIL] {msg}{Colors.ENDC}")

def log_info(msg):
    print(f"{Colors.OKBLUE}[INFO] {msg}{Colors.ENDC}")

def check_python_version():
    """Validates that the current Python interpreter is 3.11+."""
    major, minor = sys.version_info.major, sys.version_info.minor
    version_str = f"{major}.{minor}.{sys.version_info.micro}"
    log_info(f"Checking Python version... Detected: Python {version_str}")
    if major != 3 or minor < 11:
        log_fail("Python 3.11 or higher is required.")
        return False
    log_success("Python version is compatible.")
    return True

def check_dependencies():
    """Checks if all required packages declared in requirements.txt are installed."""
    log_info("Verifying packages dependency compatibility...")
    dependencies = [
        ("dotenv", "python-dotenv"),
        ("yaml", "PyYAML"),
        ("numpy", "numpy"),
        ("cv2", "opencv-python"),
        ("mediapipe", "mediapipe"),
        ("sklearn", "scikit-learn"),
        ("pygame", "pygame"),
        ("pyttsx3", "pyttsx3"),
        ("streamlit", "streamlit")
    ]
    
    missing_packages = []
    for module_name, package_name in dependencies:
        try:
            # Handle modules that have different import names
            if module_name == "dotenv":
                import dotenv
            elif module_name == "cv2":
                import cv2
            elif module_name == "sklearn":
                import sklearn
            else:
                importlib.import_module(module_name)
            log_success(f"Library '{package_name}' is installed.")
        except ImportError:
            log_fail(f"Library '{package_name}' is missing.")
            missing_packages.append(package_name)
            
    if missing_packages:
        log_fail(f"Missing dependencies: {', '.join(missing_packages)}")
        log_info("Please run: pip install -r requirements.txt")
        return False
    
    log_success("All core libraries are installed and importable.")
    return True

def check_assets_and_folders():
    """Verifies configurations and database folders are initialized correctly."""
    log_info("Verifying application file directories and assets...")
    
    # Try importing config to trigger folder initialization
    try:
        from config import config
        log_success("System folders successfully initialized via 'config.py'.")
        log_info(f"Database target path: {config.db_path}")
        log_info(f"Logging file path: {config.log_file_path}")
    except Exception as e:
        log_fail(f"Failed to import/run 'config.py': {e}")
        return False

    # Check warning sound assets
    from config import config
    sound_files = [
        ("Warning Chime", config.sound_warning_chime),
        ("Critical Alarm", config.sound_critical_alarm)
    ]
    
    for name, path in sound_files:
        if not path.exists():
            log_warning(f"{name} asset not found at '{path}'. You must place audio files before testing alarms.")
        else:
            log_success(f"{name} asset verified at '{path}'.")
            
    return True

def test_audio_subsystem():
    """Quick diagnostics check to ensure Pygame Mixer and pyttsx3 are functional."""
    log_info("Testing audio playback subsystems (Pygame Mixer & pyttsx3)...")
    
    # Test pygame mixer
    try:
        import pygame
        pygame.mixer.init()
        pygame.mixer.quit()
        log_success("Pygame Mixer initialized and closed successfully.")
    except Exception as e:
        log_warning(f"Pygame Audio Mixer check failed: {e}. Alarms may not play correctly.")

    # Test pyttsx3 engine
    try:
        import pyttsx3
        engine = pyttsx3.init()
        # Change properties briefly to ensure driver loads
        engine.setProperty('rate', 150)
        engine.setProperty('volume', 0.1) # low volume check
        log_success("pyttsx3 Voice Engine loaded successfully.")
    except Exception as e:
        log_warning(f"pyttsx3 Voice Engine check failed: {e}. Text-to-speech alerts may fail.")

    return True

def run_diagnostics():
    """Runs a complete system health-check."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}=== Driver Safety System Diagnostics ==={Colors.ENDC}\n")
    
    steps = [
        check_python_version,
        check_dependencies,
        check_assets_and_folders,
        test_audio_subsystem
    ]
    
    all_passed = True
    for step in steps:
        if not step():
            all_passed = False
            print("-" * 50)
            
    if all_passed:
        print(f"\n{Colors.OKGREEN}{Colors.BOLD}HEALTH CHECK PASSED: System is ready to run!{Colors.ENDC}\n")
    else:
        print(f"\n{Colors.FAIL}{Colors.BOLD}HEALTH CHECK FAILED: Please resolve the issues highlighted above.{Colors.ENDC}\n")
    
    return all_passed

def launch_gui():
    """Launches the Streamlit GUI dashboard."""
    log_info("Launching Streamlit GUI Dashboard...")
    try:
        # Run streamlit as a module with the active interpreter to guarantee venv context
        subprocess.run([sys.executable, "-m", "streamlit", "run", "main.py"], check=True)
    except KeyboardInterrupt:
        log_info("Streamlit dashboard terminated by user.")

def launch_cli():
    """Launches the headless CLI driver loop."""
    log_info("Launching headless CLI driver monitoring loop...")
    # Check if cli_runner.py exists before executing
    if not Path("cli_runner.py").exists():
        log_fail("cli_runner.py is not created yet. Please complete codebase setup first.")
        return
    try:
        subprocess.run([sys.executable, "cli_runner.py"], check=True)
    except KeyboardInterrupt:
        log_info("CLI monitoring loop terminated by user.")

def launch_report():
    """Generates a report for the latest completed driving session."""
    log_info("Launching report generator for the latest session...")
    try:
        from src.db.database_manager import DatabaseManager
        from src.utils.report_generator import ReportGenerator
        
        db_mgr = DatabaseManager()
        with db_mgr.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM sessions ORDER BY id DESC LIMIT 1;")
            row = cursor.fetchone()
            
        if not row:
            log_warning("No driving sessions found in database. Cannot generate report.")
            return
            
        session_id = row[0]
        log_info(f"Latest driving session ID detected: {session_id}")
        
        report_gen = ReportGenerator(db_mgr)
        report_path = report_gen.generate_report(session_id)
        if report_path:
            log_success(f"Session report successfully compiled at: {report_path}")
        else:
            log_fail("Report compilation failed.")
    except Exception as e:
        log_fail(f"Failed to generate report: {e}")

def launch_calibration():
    """Launches calibration/training helper."""
    log_info("Launching classifier training / baseline calibrator script...")
    if not Path("train_model.py").exists():
        log_fail("train_model.py is not created yet. Please complete codebase setup first.")
        return
    try:
        subprocess.run([sys.executable, "train_model.py"], check=True)
    except KeyboardInterrupt:
        log_info("Calibration script terminated by user.")

def main():
    parser = argparse.ArgumentParser(
        description="Driver Safety & Drowsiness Prevention System Central Launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python launcher.py            (Normal Mode - CLI Monitoring)
  python launcher.py --diagnose (Diagnostics Mode - Health Check)
  python launcher.py --dashboard (Dashboard Mode - Streamlit App)
  python launcher.py --train     (Training Mode - Calibrate Models)
  python launcher.py --report    (Report Mode - Export Session PDF/HTML)
        """
    )
    
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("-d", "--diagnose", action="store_true", help="Run system diagnostics health-check")
    group.add_argument("-g", "--gui", "--dashboard", dest="gui", action="store_true", help="Launch Streamlit GUI Dashboard")
    group.add_argument("-c", "--cli", "--normal", dest="cli", action="store_true", help="Launch headless CLI driver monitoring loop")
    group.add_argument("-t", "--train", action="store_true", help="Launch classifier training / calibration")
    group.add_argument("-r", "--report", action="store_true", help="Compile session safety report for the latest session")
    
    args = parser.parse_args()
    
    # If no flags are provided, default to Normal Mode (CLI)
    if not (args.diagnose or args.gui or args.cli or args.train or args.report):
        args.cli = True
        
    if args.diagnose:
        run_diagnostics()
    elif args.gui:
        if run_diagnostics():
            launch_gui()
    elif args.cli:
        if run_diagnostics():
            launch_cli()
    elif args.train:
        if run_diagnostics():
            launch_calibration()
    elif args.report:
        if run_diagnostics():
            launch_report()

if __name__ == "__main__":
    main()
