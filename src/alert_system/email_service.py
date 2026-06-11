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

    def _send_email_sync(self, driver_name: str, risk_level: str, details: str, image_path: str = None, subject: str = None, receiver: str = None):
        """Synchronous email sender meant to be executed on a background thread."""
        recipient = receiver if receiver else self.receiver_email
        
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
