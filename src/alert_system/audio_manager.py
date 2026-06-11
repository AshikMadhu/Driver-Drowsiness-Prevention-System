import pygame
from pathlib import Path
from config import config
from src.utils.logger import logger

class AudioManager:
    """Manages playing warning chimes and continuous alarm tones.
    Supports local Pygame Mixer output and online HTML5 browser audio flags.
    """
    
    def __init__(self):
        self.mixer_initialized = False
        self.warning_sound = None
        self.critical_sound = None
        
        # Audio tracks channel allocation
        self.warning_channel = None
        self.critical_channel = None
        
        self.current_volume = config.tts_volume
        
        # Browser WebRTC deployment flags
        self.play_warning_requested = False
        self.play_critical_requested = False
        
        self.initialize_mixer()

    def initialize_mixer(self):
        """Initializes the pygame audio mixer and pre-loads sound objects."""
        try:
            logger.info("Initializing Pygame Audio Mixer...")
            pygame.mixer.init()
            self.mixer_initialized = True
            
            # Setup dedicated channels
            self.warning_channel = pygame.mixer.Channel(0)
            self.critical_channel = pygame.mixer.Channel(1)
            
            # Load assets if they exist
            self._load_sounds()
            logger.info("Pygame Audio Mixer successfully initialized.")
        except Exception as e:
            logger.warning(f"Audio Manager: Failed to initialize Pygame Mixer: {e}. Pygame output bypassed. Using browser mode.")
            self.mixer_initialized = False

    def _load_sounds(self):
        """Loads WAV sound files from data directory."""
        if not self.mixer_initialized:
            return
            
        warning_path = config.sound_warning_chime
        critical_path = config.sound_critical_alarm
        
        # Load warning chime
        if warning_path.exists():
            try:
                self.warning_sound = pygame.mixer.Sound(str(warning_path))
                self.warning_sound.set_volume(self.current_volume)
            except Exception as e:
                logger.error(f"Audio Manager: Error loading warning chime '{warning_path}': {e}")
        else:
            logger.warning(f"Audio Manager: Warning chime asset not found at: {warning_path}")

        # Load critical alarm
        if critical_path.exists():
            try:
                self.critical_sound = pygame.mixer.Sound(str(critical_path))
                self.critical_sound.set_volume(self.current_volume)
            except Exception as e:
                logger.error(f"Audio Manager: Error loading critical alarm '{critical_path}': {e}")
        else:
            logger.warning(f"Audio Manager: Critical alarm asset not found at: {critical_path}")

    def play_warning_chime(self):
        """Plays a single warning chime alert (local & triggers browser flag)."""
        self.play_warning_requested = True
        if not self.mixer_initialized or not self.warning_sound:
            return
            
        try:
            # Play once (loops=0)
            self.warning_channel.play(self.warning_sound, loops=0)
        except Exception as e:
            logger.error(f"Audio Manager: Failed to play warning sound locally: {e}")

    def play_critical_alarm(self):
        """Plays the critical alarm tone on loop (local & triggers browser flag)."""
        self.play_critical_requested = True
        if not self.mixer_initialized or not self.critical_sound:
            return
            
        try:
            if not self.critical_channel.get_busy():
                logger.info("Audio Manager: Starting local continuous critical alarm loop.")
                # Play continuously (loops=-1)
                self.critical_channel.play(self.critical_sound, loops=-1)
        except Exception as e:
            logger.error(f"Audio Manager: Failed to play critical sound locally: {e}")

    def stop_critical_alarm(self):
        """Stops the looping critical alarm (local & resets browser flag)."""
        self.play_critical_requested = False
        if not self.mixer_initialized:
            return
        try:
            if self.critical_channel and self.critical_channel.get_busy():
                logger.info("Audio Manager: Stopping local continuous critical alarm loop.")
                self.critical_channel.stop()
        except Exception as e:
            logger.error(f"Audio Manager: Failed to stop critical sound locally: {e}")

    def stop_all(self):
        """Stops all playing sounds and resets requests."""
        self.play_warning_requested = False
        self.play_critical_requested = False
        if not self.mixer_initialized:
            return
        try:
            pygame.mixer.stop()
        except Exception as e:
            logger.error(f"Audio Manager: Failed to stop all sounds locally: {e}")

    def set_volume(self, volume: float):
        """Updates volume (0.0 to 1.0) dynamically."""
        self.current_volume = max(0.0, min(volume, 1.0))
        if not self.mixer_initialized:
            return
            
        if self.warning_sound:
            self.warning_sound.set_volume(self.current_volume)
        if self.critical_sound:
            self.critical_sound.set_volume(self.current_volume)

    def close(self):
        """Releases Pygame mixer resources and resets request flags."""
        self.play_warning_requested = False
        self.play_critical_requested = False
        if self.mixer_initialized:
            self.stop_all()
            try:
                pygame.mixer.quit()
                self.mixer_initialized = False
                logger.info("Audio Manager: Closed and released Pygame Mixer.")
            except Exception as e:
                logger.error(f"Audio Manager: Error during shutdown: {e}")
                
    def __del__(self):
        self.close()
