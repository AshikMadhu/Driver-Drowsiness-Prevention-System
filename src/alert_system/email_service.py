import os
import smtplib
import threading
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from config import config
from src.utils.logger import logger

class EmailService:
    """Sends emergency alert emails to designated emergency contacts asynchronously using SMTP or HTTP APIs."""
    
    def __init__(self):
        # Load SMTP settings from environment variables
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_username = os.getenv("SMTP_USERNAME", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        # Fallback recipient set to Resend sandbox account owner
        self.receiver_email = os.getenv("EMERGENCY_RECEIVER_EMAIL", "workzflow32@gmail.com")
        self.resend_api_key = os.getenv("RESEND_API_KEY", "")
        self.sendgrid_api_key = os.getenv("SENDGRID_API_KEY", "")

        # Diagnostics properties for the dashboard
        self.last_status = "Never Sent"
        self.last_timestamp = "N/A"
        self.last_provider = "N/A"
        self.last_response_code = "N/A"

        # Environment Auto-Detection
        if self.resend_api_key:
            self.active_provider = "RESEND"
            logger.info("EmailService: Auto-detected RESEND as active provider because RESEND_API_KEY exists.")
        elif self.sendgrid_api_key:
            self.active_provider = "SENDGRID"
            logger.info("EmailService: Auto-detected SENDGRID as active provider because SENDGRID_API_KEY exists.")
        else:
            self.active_provider = "SMTP"
            logger.info("EmailService: Defaulted to SMTP as active provider (no API keys detected).")

        self.status = "Pending"
        
        # Start non-blocking background connection tester
        t = threading.Thread(target=self._verify_connectivity, name="EmailServiceConnectivityTester", daemon=True)
        t.start()

    def _verify_connectivity(self):
        """Tests connection in the background to set the initial connection status."""
        try:
            if self.active_provider in ["RESEND", "SENDGRID"]:
                import requests
                url = "https://api.resend.com" if self.active_provider == "RESEND" else "https://api.sendgrid.com"
                r = requests.head(url, timeout=3.0)
                self.status = "Connected"
                logger.info(f"EmailService: Connectivity test to {self.active_provider} succeeded.")
            else:
                import socket
                logger.info(f"EmailService: Testing SMTP connection to {self.smtp_server}:{self.smtp_port}...")
                s = socket.create_connection((self.smtp_server, self.smtp_port), timeout=3.0)
                s.close()
                self.status = "Connected"
                logger.info("EmailService: SMTP connectivity test succeeded.")
        except Exception as e:
            logger.warning(f"EmailService: Connectivity check failed for {self.active_provider}: {e}")
            self.status = "Failed"
            
            # Fallback checking on startup
            if self.active_provider == "SMTP" and (self.resend_api_key or self.sendgrid_api_key):
                self.active_provider = "RESEND" if self.resend_api_key else "SENDGRID"
                logger.info(f"EmailService: SMTP failed connection on startup. Falling back to {self.active_provider} API.")
                try:
                    import requests
                    url = "https://api.resend.com" if self.active_provider == "RESEND" else "https://api.sendgrid.com"
                    requests.head(url, timeout=3.0)
                    self.status = "Connected"
                except Exception as api_err:
                    logger.error(f"EmailService: Fallback provider connection check failed: {api_err}")
                    self.status = "Failed"

    def _send_email_via_smtp(self, driver_name: str, risk_level: str, details: str, image_path: str, subject: str, recipient: str) -> bool:
        """Sends email synchronously using SMTP library."""
        self.last_provider = "SMTP"
        self.last_timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        try:
            msg = MIMEMultipart()
            msg['From'] = self.smtp_username
            msg['To'] = recipient
            msg['Subject'] = subject if subject else f"⚠️ CRITICAL EMERGENCY: Driver Safety Alert - {driver_name}"
            
            body = f"""
            CRITICAL DRIVER SAFETY ALERT
            --------------------------------------------------
            Driver Profile:       {driver_name}
            Safety Risk Status:   {risk_level.upper()}
            Timestamp:            {time.strftime('%Y-%m-%d %H:%M:%S')}
            
            Description:
            The driver safety system has identified a safety violation or alert threshold escalation.
            
            Session Telemetry Summary:
            {details}
            
            --------------------------------------------------
            This is an automated warning dispatched by the Driver Safety & Drowsiness Prevention System.
            """
            msg.attach(MIMEText(body, 'plain'))
            
            if image_path and os.path.exists(image_path):
                try:
                    with open(image_path, 'rb') as f:
                        img_data = f.read()
                    image_part = MIMEImage(img_data, name=os.path.basename(image_path))
                    image_part.add_header('Content-Disposition', 'attachment', filename=os.path.basename(image_path))
                    msg.attach(image_part)
                    logger.info(f"EmailService: Attached screenshot to email: {image_path}")
                except Exception as img_err:
                    logger.error(f"EmailService: Failed to attach image: {img_err}")
            
            logger.info(f"EmailService: Dispatching email via SMTP: {self.smtp_server}:{self.smtp_port}...")
            server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=10.0)
            server.starttls()
            server.login(self.smtp_username, self.smtp_password)
            server.sendmail(self.smtp_username, recipient, msg.as_string())
            server.quit()
            
            logger.info("EmailService: SMTP email dispatch successful.")
            self.last_status = "Success"
            self.last_response_code = "250 OK"
            return True
        except Exception as e:
            logger.error(f"EmailService: SMTP email dispatch failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.last_status = "Failed"
            self.last_response_code = f"Error: {str(e)[:30]}"
            return False

    def _send_email_via_resend(self, driver_name: str, risk_level: str, details: str, image_path: str, subject: str, recipient: str) -> bool:
        """Sends email synchronously using Resend API (HTTPS)."""
        import requests
        import base64
        
        self.last_provider = "RESEND"
        self.last_timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        
        url = "https://api.resend.com/emails"
        headers = {
            "Authorization": f"Bearer {self.resend_api_key}",
            "Content-Type": "application/json"
        }
        
        email_subject = subject if subject else f"⚠️ CRITICAL EMERGENCY: Driver Safety Alert - {driver_name}"
        
        body = f"""
        CRITICAL DRIVER SAFETY ALERT
        --------------------------------------------------
        Driver Profile:       {driver_name}
        Safety Risk Status:   {risk_level.upper()}
        Timestamp:            {time.strftime('%Y-%m-%d %H:%M:%S')}
        
        Description:
        The driver safety system has identified a safety violation or alert threshold escalation.
        
        Session Telemetry Summary:
        {details}
        
        --------------------------------------------------
        This is an automated warning dispatched by the Driver Safety & Drowsiness Prevention System.
        """
        
        payload = {
            "from": "DMS Alert <onboarding@resend.dev>",
            "to": [recipient],
            "subject": email_subject,
            "text": body
        }
        
        if image_path and os.path.exists(image_path):
            try:
                with open(image_path, "rb") as f:
                    content_b64 = base64.b64encode(f.read()).decode("utf-8")
                payload["attachments"] = [{
                    "filename": os.path.basename(image_path),
                    "content": content_b64
                }]
                logger.info(f"EmailService: Attached screenshot base64 for Resend: {image_path}")
            except Exception as e:
                logger.error(f"EmailService: Resend failed to read attachment: {e}")
                
        try:
            logger.info("EmailService: Dispatching email via Resend API (HTTPS)...")
            r = requests.post(url, json=payload, headers=headers, timeout=10.0)
            
            logger.info(f"EmailService: Resend API response code: {r.status_code}")
            logger.info(f"EmailService: Resend API response body: {r.text}")
            
            self.last_response_code = str(r.status_code)
            
            if r.status_code in [200, 201, 202]:
                try:
                    resp_json = r.json()
                    msg_id = resp_json.get("id", "Unknown ID")
                    logger.info(f"EmailService: Direct Resend API dispatch successful. Message ID: {msg_id}")
                    self.last_response_code = f"{r.status_code} (ID: {msg_id[:8]})"
                except Exception:
                    logger.info("EmailService: Direct Resend API dispatch successful.")
                self.last_status = "Success"
                return True
            else:
                logger.error(f"EmailService: Resend API returned status code {r.status_code}: {r.text}")
                self.last_status = "Failed"
                return False
        except Exception as e:
            logger.error(f"EmailService: Resend API post failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.last_status = "Failed"
            self.last_response_code = f"Error: {str(e)[:30]}"
            return False

    def _send_email_via_sendgrid(self, driver_name: str, risk_level: str, details: str, image_path: str, subject: str, recipient: str) -> bool:
        """Sends email synchronously using SendGrid API (HTTPS)."""
        import requests
        import base64
        
        self.last_provider = "SENDGRID"
        self.last_timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        
        url = "https://api.sendgrid.com/v3/mail/send"
        headers = {
            "Authorization": f"Bearer {self.sendgrid_api_key}",
            "Content-Type": "application/json"
        }
        
        email_subject = subject if subject else f"⚠️ CRITICAL EMERGENCY: Driver Safety Alert - {driver_name}"
        
        body = f"""
        CRITICAL DRIVER SAFETY ALERT
        --------------------------------------------------
        Driver Profile:       {driver_name}
        Safety Risk Status:   {risk_level.upper()}
        Timestamp:            {time.strftime('%Y-%m-%d %H:%M:%S')}
        
        Description:
        The driver safety system has identified a safety violation or alert threshold escalation.
        
        Session Telemetry Summary:
        {details}
        
        --------------------------------------------------
        This is an automated warning dispatched by the Driver Safety & Drowsiness Prevention System.
        """
        
        sender_email = self.smtp_username if self.smtp_username else "workzflow32@gmail.com"
        
        payload = {
            "personalizations": [{"to": [{"email": recipient}]}],
            "from": {"email": sender_email},
            "subject": email_subject,
            "content": [{"type": "text/plain", "value": body}]
        }
        
        if image_path and os.path.exists(image_path):
            try:
                with open(image_path, "rb") as f:
                    content_b64 = base64.b64encode(f.read()).decode("utf-8")
                payload["attachments"] = [{
                    "content": content_b64,
                    "type": "image/jpeg",
                    "filename": os.path.basename(image_path)
                }]
                logger.info(f"EmailService: Attached screenshot base64 for SendGrid: {image_path}")
            except Exception as e:
                logger.error(f"EmailService: SendGrid failed to read attachment: {e}")
                
        try:
            logger.info("EmailService: Dispatching email via SendGrid API (HTTPS)...")
            r = requests.post(url, json=payload, headers=headers, timeout=10.0)
            
            logger.info(f"EmailService: SendGrid API response code: {r.status_code}")
            logger.info(f"EmailService: SendGrid API response body: {r.text}")
            
            self.last_response_code = str(r.status_code)
            
            if r.status_code in [200, 201, 202]:
                logger.info("EmailService: SendGrid API dispatch successful.")
                self.last_status = "Success"
                return True
            else:
                logger.error(f"EmailService: SendGrid API returned status code {r.status_code}: {r.text}")
                self.last_status = "Failed"
                return False
        except Exception as e:
            logger.error(f"EmailService: SendGrid API post failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.last_status = "Failed"
            self.last_response_code = f"Error: {str(e)[:30]}"
            return False

    def _send_email_sync(self, driver_name: str, risk_level: str, details: str, image_path: str = None, subject: str = None, receiver: str = None):
        """Synchronous email sender meant to be executed on a background thread. Coordinates failover."""
        recipient = receiver if receiver else self.receiver_email
        success = False
        
        # 1. Dispatch using the active provider
        if self.active_provider == "RESEND" and self.resend_api_key:
            success = self._send_email_via_resend(driver_name, risk_level, details, image_path, subject, recipient)
        elif self.active_provider == "SENDGRID" and self.sendgrid_api_key:
            success = self._send_email_via_sendgrid(driver_name, risk_level, details, image_path, subject, recipient)
        elif self.active_provider == "SMTP" and self.smtp_username and self.smtp_password:
            success = self._send_email_via_smtp(driver_name, risk_level, details, image_path, subject, recipient)
            
            # 2. Failover logic if SMTP failed
            if not success:
                logger.warning("EmailService: SMTP dispatch failed. Attempting failover checks...")
                if self.resend_api_key:
                    logger.info("EmailService: Found RESEND_API_KEY. Triggering failover to Resend API...")
                    self.active_provider = "RESEND"
                    success = self._send_email_via_resend(driver_name, risk_level, details, image_path, subject, recipient)
                elif self.sendgrid_api_key:
                    logger.info("EmailService: Found SENDGRID_API_KEY. Triggering failover to SendGrid API...")
                    self.active_provider = "SENDGRID"
                    success = self._send_email_via_sendgrid(driver_name, risk_level, details, image_path, subject, recipient)
                else:
                    logger.error("EmailService: SMTP failed and no HTTP API keys (Resend/SendGrid) are available for failover.")
        else:
            logger.warning(f"EmailService: Configurations are incomplete for active provider {self.active_provider}. Dispatch bypassed.")
            self.last_status = "Failed"
            self.last_response_code = "Incomplete Config"
            self.last_provider = self.active_provider
            self.last_timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            
        if success:
            self.status = "Connected"
        else:
            self.status = "Failed"

    def send_emergency_alert(self, driver_name: str, risk_level: str, details: str, image_path: str = None, subject: str = None, receiver: str = None):
        """Triggers emergency email dispatch asynchronously using a background thread."""
        thread = threading.Thread(
            target=self._send_email_sync,
            args=(driver_name, risk_level, details, image_path, subject, receiver),
            name="EmailSenderThread",
            daemon=True
        )
        thread.start()
        logger.info("EmailService: Dispatched email task to worker thread.")
