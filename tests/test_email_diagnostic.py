import os
import sys
import time
import socket
import smtplib
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

# Load local .env if exists
load_dotenv(BASE_DIR / ".env")

def run_diagnostic():
    print("=" * 60)
    print("           DMS SMTP DIAGNOSTIC DELIVERY VERIFIER          ")
    print("=" * 60)
    
    server_host = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    port_str = os.getenv("SMTP_PORT", "587")
    username = os.getenv("SMTP_USERNAME", "")
    password = os.getenv("SMTP_PASSWORD", "")
    receiver = os.getenv("EMERGENCY_RECEIVER_EMAIL", "ashiksjc2025@gmail.com")
    
    # Environment variables
    container_id = socket.gethostname()
    os_env = sys.platform
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    
    print(f"[*] Timestamp:     {timestamp}")
    print(f"[*] Hostname:      {container_id}")
    print(f"[*] Environment:   {os_env}")
    print(f"[*] SMTP Server:   {server_host}:{port_str}")
    print(f"[*] SMTP Username: {username}")
    print(f"[*] Recipient:     {receiver}")
    
    try:
        port = int(port_str)
        print("[*] Instantiating SMTP socket connection...")
        server = smtplib.SMTP(server_host, port, timeout=10.0)
        
        # Enable complete SMTP protocol debugging to stdout
        server.set_debuglevel(1)
        
        print("[*] Connecting and sending EHLO...")
        server.ehlo()
        
        print("[*] Upgrading connection to secure TLS (STARTTLS)...")
        server.starttls()
        server.ehlo()
        
        print("[*] Logging in...")
        server.login(username, password)
        
        print("[*] Constructing MIME container...")
        msg = MIMEMultipart()
        msg['From'] = username
        msg['To'] = receiver
        msg['Subject'] = f"🚨 HF Delivery Test - {timestamp}"
        
        body = f"""
        HUGGING FACE SMTP DIAGNOSTIC DELIVERY VERIFICATION
        --------------------------------------------------
        Timestamp:    {timestamp}
        Container ID: {container_id}
        Environment:  {os_env}
        Python:       {sys.version}
        
        This is a diagnostic verification email sent directly from the DMS SMTP test script.
        """
        msg.attach(MIMEText(body, 'plain'))
        
        print("[*] Dispatching mail transaction...")
        ref_code = server.sendmail(username, receiver, msg.as_string())
        print(f"[OK] Mail transaction finished. Return code/response: {ref_code}")
        
        server.quit()
        print("[OK] SMTP session terminated cleanly.")
        return True, "Success", ref_code
    except Exception as e:
        print(f"\n[FAIL] SMTP diagnostic run failed: {e}")
        import traceback
        traceback.print_exc()
        return False, str(e), None

if __name__ == "__main__":
    run_diagnostic()
