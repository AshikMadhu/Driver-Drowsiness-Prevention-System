import os
import sys
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from dotenv import load_dotenv

# Add root folder to python path to resolve imports
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

# Ensure environment variables are loaded
load_dotenv(BASE_DIR / ".env")

def run_direct_smtp_test():
    print("=" * 60)
    print("               ISOLATED DIRECT SMTP TEST RUNNER             ")
    print("=" * 60)
    
    # Load configuration
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port_str = os.getenv("SMTP_PORT", "587")
    smtp_username = os.getenv("SMTP_USERNAME", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    receiver_email = os.getenv("EMERGENCY_RECEIVER_EMAIL", "ashiksjc2025@gmail.com")
    
    connection_status = "PENDING"
    auth_status = "PENDING"
    delivery_status = "PENDING"
    exception_details = "None"
    connection_time_ms = 0.0
    
    try:
        port = int(smtp_port_str)
        t_start = time.time()
        
        # 1. Connection
        print("[*] Connecting to SMTP Server...")
        server = smtplib.SMTP(smtp_server, port, timeout=10.0)
        connection_status = "SUCCESS"
        connection_time_ms = (time.time() - t_start) * 1000
        print(f"  [OK] Connected successfully in {connection_time_ms:.1f}ms")
        
        # Upgrade connection
        print("[*] Upgrading connection to secure TLS...")
        server.starttls()
        
        # 2. Authentication
        print("[*] Authenticating...")
        server.login(smtp_username, smtp_password)
        auth_status = "SUCCESS"
        print("  [OK] SMTP Authentication successful.")
        
        # 3. Delivery
        print("[*] Preparing MIME Message Container...")
        msg = MIMEMultipart()
        msg['From'] = smtp_username
        msg['To'] = receiver_email
        msg['Subject'] = f"🚨 DMS Isolated SMTP Direct Test - {time.strftime('%H:%M:%S')}"
        
        body = f"""
        DMS ISOLATED SMTP DIRECT TEST REPORT
        ----------------------------------------------
        Timestamp:        {time.strftime('%Y-%m-%d %H:%M:%S')}
        SMTP Server:      {smtp_server}:{port}
        Sender:           {smtp_username}
        Recipient:        {receiver_email}
        
        This test verifies SMTP channel reliability directly from Python's smtplib.
        """
        msg.attach(MIMEText(body, 'plain'))
        
        print("[*] Sending Email...")
        server.sendmail(smtp_username, receiver_email, msg.as_string())
        delivery_status = "SUCCESS"
        print("  [OK] Email sent successfully.")
        
        server.quit()
        
    except Exception as e:
        exception_details = f"{type(e).__name__}: {str(e)}"
        print(f"  [FAIL] SMTP Test failed: {e}")
        if connection_status == "PENDING":
            connection_status = "FAILED"
        if auth_status == "PENDING" and connection_status == "SUCCESS":
            auth_status = "FAILED"
        if delivery_status == "PENDING" and auth_status == "SUCCESS":
            delivery_status = "FAILED"
            
    # Compile the test report
    report_content = f"""# SMTP Direct Test Report

This document reports the connection, security authentication, and email delivery results from the isolated SMTP direct channel verification script.

---

## 📊 Summary of SMTP Test Run

* **Execution Timestamp**: {time.strftime('%Y-%m-%d %H:%M:%S')}
* **SMTP Host Target**: `{smtp_server}:{smtp_port_str}`
* **Active Sender**: `{smtp_username}`
* **Target Recipient**: `{receiver_email}`
* **Handshake TLS Connection Speed**: {connection_time_ms:.1f} ms

---

## 🔒 Channel Verification Status

| Step | Verification Criteria | Status |
| :--- | :--- | :---: |
| **1** | SMTP Server TCP Connection | `{connection_status}` |
| **2** | SMTP login Authentication | `{auth_status}` |
| **3** | SMTP Transaction Email Delivery | `{delivery_status}` |

---

## 🔍 Exception Details

```
{exception_details}
```

---

## 🛠️ Verification Diagnostic Verdict

{"*All tests passed successfully. The direct SMTP connection, login, and delivery are fully functional and operational.*" if delivery_status == "SUCCESS" else "*SMTP test failed. Refer to the exception details above to diagnose connection and credential issues.*"}
"""

    # Save report in artifacts folder
    artifact_path = BASE_DIR.parent.parent / ".gemini" / "antigravity" / "brain" / "a2fd11d7-506b-4b5b-ba96-38470904ace1" / "SMTP_TEST_REPORT.md"
    try:
        with open(artifact_path, "w", encoding="utf-8") as f:
            f.write(report_content)
        print(f"[OK] SMTP test report saved successfully to {artifact_path}")
    except Exception as e:
        print(f"Error saving SMTP test report: {e}")

if __name__ == "__main__":
    run_direct_smtp_test()
