import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

# Load .env variables
load_dotenv(BASE_DIR / ".env")

from src.alert_system.email_service import EmailService

def run_hybrid_diagnostics():
    print("=" * 60)
    print("        DMS EMAIL SERVICE HYBRID DIAGNOSTIC TEST         ")
    print("=" * 60)
    
    # -------------------------------------------------------------
    # Test 1: SMTP default configuration
    # -------------------------------------------------------------
    print("\n[*] Scenario 1: Standard Local Setup (Default SMTP)")
    # Clear any RESEND/SENDGRID keys from os.environ for this test
    old_resend = os.environ.pop("RESEND_API_KEY", None)
    old_sendgrid = os.environ.pop("SENDGRID_API_KEY", None)
    
    svc = EmailService()
    # Wait for the background connectivity thread to complete
    time.sleep(4.0)
    
    print(f"  Detected Active Provider: {svc.active_provider} (Expected: SMTP)")
    print(f"  Connection Status:        {svc.status} (Expected: Connected)")
    
    # Restore keys if they existed
    if old_resend:
        os.environ["RESEND_API_KEY"] = old_resend
    if old_sendgrid:
        os.environ["SENDGRID_API_KEY"] = old_sendgrid
        
    # -------------------------------------------------------------
    # Test 2: Resend API Auto-Detection (Cloud Space simulation)
    # -------------------------------------------------------------
    print("\n[*] Scenario 2: Cloud Simulation (RESEND_API_KEY present)")
    os.environ["RESEND_API_KEY"] = "re_mock_api_key_12345"
    
    svc_resend = EmailService()
    time.sleep(4.0)
    
    print(f"  Detected Active Provider: {svc_resend.active_provider} (Expected: RESEND)")
    print(f"  Connection Status:        {svc_resend.status} (Expected: Connected - reachability test to api.resend.com)")
    
    # Clean up
    if not old_resend:
        os.environ.pop("RESEND_API_KEY", None)
    else:
        os.environ["RESEND_API_KEY"] = old_resend

    # -------------------------------------------------------------
    # Test 3: SMTP Failure and Failover to RESEND Simulation
    # -------------------------------------------------------------
    print("\n[*] Scenario 3: Failover (SMTP Port Blocks -> Fallback to RESEND)")
    # Set up bad SMTP server to force failure, but provide RESEND key
    os.environ["RESEND_API_KEY"] = "re_mock_api_key_12345"
    
    svc_failover = EmailService()
    # Manually overwrite SMTP settings to invalid values
    svc_failover.smtp_server = "invalid.smtp.domain"
    svc_failover.smtp_port = 999
    # Make active provider SMTP to test dispatcher fallback
    svc_failover.active_provider = "SMTP"
    
    print("  Triggering email alert with bad SMTP config...")
    # Trigger dispatch (non-blocking)
    svc_failover.send_emergency_alert(
        driver_name="TestFailoverDriver",
        risk_level="Critical",
        details="Testing failover logic simulation.",
        subject="Test Failover Alert"
    )
    
    # Wait for dispatch thread
    time.sleep(5.0)
    
    print(f"  After Dispatch - Active Provider: {svc_failover.active_provider} (Expected: RESEND)")
    print(f"  After Dispatch - Status:          {svc_failover.status} (Expected: Failed - due to mock key)")
    
    # Clean up
    if not old_resend:
        os.environ.pop("RESEND_API_KEY", None)
    else:
        os.environ["RESEND_API_KEY"] = old_resend

    print("\n" + "=" * 60)
    print("            HYBRID DIAGNOSTIC COMPLETED RUN             ")
    print("=" * 60)

if __name__ == "__main__":
    run_hybrid_diagnostics()
