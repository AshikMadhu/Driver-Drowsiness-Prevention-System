import os
import smtplib
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from config import config
from src.utils.logger import logger

class EmailService:
    """Sends emergency alert emails to designated emergency contacts asynchronously."""
    
    def __init__(self):
        # Load SMTP settings from environment variables
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_username = os.getenv("SMTP_USERNAME", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.receiver_email = os.getenv("EMERGENCY_RECEIVER_EMAIL", "ashiksjc2025@gmail.com")
        self.resend_api_key = os.getenv("RESEND_API_KEY", "")
        self.sendgrid_api_key = os.getenv("SENDGRID_API_KEY", "")

    def _send_email_sync(self, driver_name: str, risk_level: str, details: str, image_path: str = None, subject: str = None, receiver: str = None):
        """Synchronous email sender meant to be executed on a background thread."""
        recipient = receiver if receiver else self.receiver_email
        
        # Check for HTTP API bypass (ideal for Hugging Face Spaces where SMTP ports are blocked)
        if self.resend_api_key:
            logger.info("EmailService: Found RESEND_API_KEY. Directing email dispatch via HTTPS Resend API.")
            self._send_email_via_resend(driver_name, risk_level, details, image_path, subject, recipient)
            return
            
        if self.sendgrid_api_key:
            logger.info("EmailService: Found SENDGRID_API_KEY. Directing email dispatch via HTTPS SendGrid API.")
            self._send_email_via_sendgrid(driver_name, risk_level, details, image_path, subject, recipient)
            return
            
        # Safety checks
        if not self.smtp_username or not self.smtp_password or not recipient:
            logger.warning("EmailService: SMTP configurations are incomplete. Bypassing email dispatch.")
            return

        logger.info(f"EmailService: Preparing emergency email alert to '{recipient}'...")
        
        try:
            import time
            # Create message container
            msg = MIMEMultipart()
            msg['From'] = self.smtp_username
            msg['To'] = recipient
            msg['Subject'] = subject if subject else f"⚠️ CRITICAL EMERGENCY: Driver Safety Alert - {driver_name}"
            
            # Format email body text
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
            
            # Attach screenshot if available
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
            
            # Connect to SMTP server and send
            server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=10.0)
            server.starttls() # Secure connection handshake
            server.login(self.smtp_username, self.smtp_password)
            server.sendmail(self.smtp_username, recipient, msg.as_string())
            server.quit()
            
            logger.info("EmailService: Emergency email dispatch successful.")
        except Exception as e:
            logger.error(f"EmailService: Failed to dispatch emergency email: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def send_emergency_alert(self, driver_name: str, risk_level: str, details: str, image_path: str = None, subject: str = None, receiver: str = None):
        """
        Triggers emergency email dispatch asynchronously using a background thread.
        """
        # Spawn thread immediately to prevent camera blockages
        thread = threading.Thread(
            target=self._send_email_sync,
            args=(driver_name, risk_level, details, image_path, subject, receiver),
            name="EmailSenderThread",
            daemon=True
        )
        thread.start()
        logger.info("EmailService: Dispatched SMTP email task to worker thread.")

    def _send_email_via_resend(self, driver_name: str, risk_level: str, details: str, image_path: str, subject: str, recipient: str):
        import requests
        import base64
        import time
        
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
            r = requests.post(url, json=payload, headers=headers, timeout=10.0)
            if r.status_code in [200, 201, 202]:
                logger.info("EmailService: Direct Resend API dispatch successful.")
            else:
                logger.error(f"EmailService: Resend API returned status code {r.status_code}: {r.text}")
        except Exception as e:
            logger.error(f"EmailService: Resend API post failed: {e}")

    def _send_email_via_sendgrid(self, driver_name: str, risk_level: str, details: str, image_path: str, subject: str, recipient: str):
        import requests
        import base64
        import time
        
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
            r = requests.post(url, json=payload, headers=headers, timeout=10.0)
            if r.status_code in [200, 201, 202]:
                logger.info("EmailService: SendGrid API dispatch successful.")
            else:
                logger.error(f"EmailService: SendGrid API returned status code {r.status_code}: {r.text}")
        except Exception as e:
            logger.error(f"EmailService: SendGrid API post failed: {e}")
