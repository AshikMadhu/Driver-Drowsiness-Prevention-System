from config import config
from src.utils.logger import logger

class VoiceAlert:
    """Asynchronous browser-compatible voice alerting system.
    Tracks speech requests via thread-safe flags to trigger Speech Synthesis API in the browser.
    """
    
    def __init__(self):
        self.speech_requested = False
        self.speech_to_play = ""
        self.current_rate = config.tts_rate
        self.current_volume = config.tts_volume
        logger.info("VoiceAlert: Browser voice alerting system initialized.")

    def speak(self, text: str, clear_queue: bool = True):
        """Enqueues a text string to be spoken in the browser."""
        logger.info(f"VoiceAlert speaking: '{text}'")
        self.speech_to_play = text
        self.speech_requested = True

    def stop(self):
        """Stops any pending speech request."""
        self.speech_requested = False
        self.speech_to_play = ""

    def close(self):
        """Alias for stop to support clean teardown."""
        self.stop()

