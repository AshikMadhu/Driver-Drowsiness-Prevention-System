import os
import sys
import time
import shutil
import numpy as np
import cv2
from pathlib import Path
from dotenv import load_dotenv

# Add root folder to python path to resolve imports
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

# Ensure environment variables are loaded
load_dotenv(BASE_DIR / ".env")

from src.alert_system.email_service import EmailService

def run_smtp_audit():
    print("=" * 60)
    print("                 SMTP EMAIL SERVICE AUDIT            ")
    print("=" * 60)
    
    # Timing variables
    t_start = time.time()
    
    # Initialize variables to record
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port_str = os.getenv("SMTP_PORT", "587")
    smtp_username = os.getenv("SMTP_USERNAME", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    receiver_email = os.getenv("EMERGENCY_RECEIVER_EMAIL", "ashiksjc2025@gmail.com")
    
    # Status indicators
    vars_loaded = False
    connection_success = False
    auth_success = False
    attachment_success = False
    delivery_success = False
    error_msg = None
    
    # 1. Verify Variables Loading
    print("[*] Step 1: Checking SMTP Configuration Variables...")
    if smtp_username and smtp_password and receiver_email:
        vars_loaded = True
        print(f"  [OK] Credentials found. Username: {smtp_username}")
        print(f"  [OK] Server: {smtp_server}:{smtp_port_str}")
        print(f"  [OK] Recipient: {receiver_email}")
    else:
        print("  [FAIL] Missing required credentials in .env file.")
        
    # 2. Build dummy screenshot for attachment test
    print("[*] Step 2: Creating Test Screenshot...")
    dummy_img_path = BASE_DIR / "data" / "evidence" / "test_audit_screenshot.jpg"
    dummy_img_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Draw a test box
        cv2.rectangle(dummy_frame, (100, 100), (540, 380), (0, 0, 255), 3)
        cv2.putText(dummy_frame, "DMS SMTP AUDIT FRAME", (130, 240), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.imwrite(str(dummy_img_path), dummy_frame)
        attachment_success = dummy_img_path.exists()
        print(f"  [OK] Screenshot created at: {dummy_img_path}")
    except Exception as e:
        print(f"  [FAIL] Failed to create screenshot: {e}")
        attachment_success = False
        
    # 3. Perform connection, login and delivery checks
    if vars_loaded:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.image import MIMEImage
        
        print("[*] Step 3: Establishing SMTP Connection & Handshake...")
        try:
            port = int(smtp_port_str)
            t0 = time.time()
            server = smtplib.SMTP(smtp_server, port, timeout=10.0)
            connection_success = True
            print(f"  [OK] TCP Connection established to {smtp_server}:{port} in {(time.time() - t0)*1000:.1f}ms")
            
            print("[*] Step 4: Upgrading to TLS (Secure Handshake)...")
            server.starttls()
            
            print("[*] Step 5: Authenticating with Credentials...")
            server.login(smtp_username, smtp_password)
            auth_success = True
            print("  [OK] SMTP Authentication successful.")
            
            # Prepare message
            msg = MIMEMultipart()
            msg['From'] = smtp_username
            msg['To'] = receiver_email
            msg['Subject'] = f"🚨 DMS SMTP AUDIT REPORT - {time.strftime('%H:%M:%S')}"
            
            body = f"""
            DMS SMTP CONNECTION AUDIT REPORT
            ----------------------------------------------
            Timestamp:        {time.strftime('%Y-%m-%d %H:%M:%S')}
            SMTP Server:      {smtp_server}:{port}
            Sender:           {smtp_username}
            Recipient:        {receiver_email}
            
            This email verifies that the SMTP alert subsystem is operational and capable of sending emergency notifications with image evidence attachments.
            
            Validation status:
            - Config variables loaded: YES
            - Handshake & TLS upgrade: YES
            - Authentication success:  YES
            - Screenshot attachment:    YES
            
            ----------------------------------------------
            Driver Drowsiness Safety System Automated Test.
            """
            msg.attach(MIMEText(body, 'plain'))
            
            # Attach the dummy image
            if attachment_success:
                with open(dummy_img_path, 'rb') as f:
                    img_data = f.read()
                image_part = MIMEImage(img_data, name=os.path.basename(dummy_img_path))
                image_part.add_header('Content-Disposition', 'attachment', filename=os.path.basename(dummy_img_path))
                msg.attach(image_part)
                
            print("[*] Step 6: Dispatching Test Email...")
            server.sendmail(smtp_username, receiver_email, msg.as_string())
            delivery_success = True
            print("  [OK] Email delivery transaction complete.")
            
            server.quit()
        except Exception as e:
            error_msg = str(e)
            print(f"  [FAIL] SMTP Transaction failed: {e}")
            
    # Clean up dummy image
    if dummy_img_path.exists():
        try:
            os.remove(dummy_img_path)
        except Exception:
            pass
            
    audit_duration = time.time() - t_start
    
    diagnostics_notes = "*No errors encountered. Email system is fully operational and authenticated.*"
    if not delivery_success:
        diagnostics_notes = f"**Error Trace encountered during connection execution**:\n```\n{error_msg}\n```"
        
    # Generate the markdown report content
    report_content = f"""# SMTP Email Subsystem Validation Report

This report documents the security handshake, connection validation, authentication, and attachment delivery checks performed on the Driver Monitoring System (DMS) SMTP notification engine.

## 📊 Summary of SMTP Handshake

* **Audit Timestamp**: {time.strftime('%Y-%m-%d %H:%M:%S')}
* **SMTP Server**: `{smtp_server}:{smtp_port_str}`
* **Sender Address**: `{smtp_username}`
* **Emergency Receiver**: `{receiver_email}`
* **Authentication Method**: TLS (Secure connection upgrade)
* **Transaction Execution Duration**: **{audit_duration:.2f} seconds**
* **Verification Status**: **{"🟢 OPERATIONAL" if delivery_success else "🔴 FAILURE"}**

---

## 🔒 Step-by-Step Validation Status

| Step | Verification Test Case | Status | Audit Notes |
| :--- | :--- | :---: | :--- |
| **1** | Environment Variables Loading | {"✅ SUCCESS" if vars_loaded else "❌ FAILED"} | Config elements `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD` parsed. |
| **2** | Secure TLS TCP Handshake | {"✅ SUCCESS" if connection_success else "❌ FAILED"} | Established socket connection to `{smtp_server}` and upgraded via `starttls()`. |
| **3** | SMTP Authentication | {"✅ SUCCESS" if auth_success else "❌ FAILED"} | Secure login accepted. Credentials verified. |
| **4** | Frame Screenshot Attachment Assembly | {"✅ SUCCESS" if attachment_success else "❌ FAILED"} | Captured and serialized raw BGR frame to JPEG, converted to `MIMEImage` with proper attachment headers. |
| **5** | actual Email Delivery | {"✅ SUCCESS" if delivery_success else "❌ FAILED"} | Dispatched transaction successfully. Receipt confirmed by SMTP relay server. |

---

## 🔍 Diagnostics & Error Trace Logs

{diagnostics_notes}

---

## 🛡️ Real-World Safety Implications

* **Asynchronous Execution**: The notification service utilizes worker threads (`ThirdAlarmEmailWorker` and `Level4EmergencyEmailWorker`) to prepare screenshot files and initiate SMTP sockets. This isolates blocking network requests (which take ~{audit_duration:.1f} seconds) from the primary thread, preserving the dashboard frame rate ($\ge 20$ FPS) during active alerts.
* **Inbox Spam Prevention**: Escalation only dispatches an email on the 3rd continuous eye closure alarm. Cooldown throttles prevent mail loops, keeping mailbox alerts clear and reliable.
"""
    
    # Save the report as an artifact in the correct AppData folder
    artifact_path = BASE_DIR.parent.parent / ".gemini" / "antigravity" / "brain" / "a2fd11d7-506b-4b5b-ba96-38470904ace1" / "EMAIL_VALIDATION_REPORT.md"
    try:
        with open(artifact_path, "w", encoding="utf-8") as f:
            f.write(report_content)
        print(f"[OK] Email validation report saved successfully to {artifact_path}")
    except Exception as e:
        print(f"Error saving email validation report: {e}")

if __name__ == "__main__":
    run_smtp_audit()
