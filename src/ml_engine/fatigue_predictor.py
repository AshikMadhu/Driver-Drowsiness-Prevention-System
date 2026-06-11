import pickle
import numpy as np
from pathlib import Path
from typing import Dict, Any, Optional
from config import config
from src.utils.logger import logger

class FatiguePredictor:
    """Uses pre-trained Scikit-Learn models to predict driver fatigue based on physiological metrics."""
    
    def __init__(self, model_dir: Path = config.db_path.parent / "models"):
        self.model_dir = model_dir
        self.model_dir.mkdir(parents=True, exist_ok=True)
        
        self.scaler_path = self.model_dir / "scaler.pkl"
        self.lr_path = self.model_dir / "fatigue_model_lr.pkl"
        self.rf_path = self.model_dir / "fatigue_model_rf.pkl"
        
        self.scaler = None
        self.model_lr = None
        self.model_rf = None
        self.models_loaded = False
        
        self.load_models()

    def load_models(self) -> bool:
        """Loads StandardScaler and model objects from disk."""
        if not (self.scaler_path.exists() and self.lr_path.exists() and self.rf_path.exists()):
            logger.warning("FatiguePredictor: Model files do not exist. Attempting auto-calibration...")
            return self.auto_calibrate()
            
        try:
            with open(self.scaler_path, 'rb') as f:
                self.scaler = pickle.load(f)
            with open(self.lr_path, 'rb') as f:
                self.model_lr = pickle.load(f)
            with open(self.rf_path, 'rb') as f:
                self.model_rf = pickle.load(f)
                
            self.models_loaded = True
            logger.info("FatiguePredictor: Successfully loaded scaler and model weights (LR & RF).")
            return True
        except Exception as e:
            logger.error(f"FatiguePredictor: Failed to load models: {e}. Attempting auto-calibration...")
            return self.auto_calibrate()

    def auto_calibrate(self) -> bool:
        """Automatically runs the training pipeline to generate compatible model weights."""
        try:
            import importlib
            # Dynamically import to avoid circular dependencies
            train_module = importlib.import_module("train_model")
            train_module.train_and_evaluate_fatigue_models(model_dir=self.model_dir)
            
            # Reload files
            with open(self.scaler_path, 'rb') as f:
                self.scaler = pickle.load(f)
            with open(self.lr_path, 'rb') as f:
                self.model_lr = pickle.load(f)
            with open(self.rf_path, 'rb') as f:
                self.model_rf = pickle.load(f)
                
            self.models_loaded = True
            logger.info("FatiguePredictor: Auto-calibration completed successfully.")
            return True
        except Exception as ex:
            logger.error(f"FatiguePredictor: Auto-calibration failed: {ex}")
            self.models_loaded = False
            return False

    def predict(
        self,
        blink_freq: float,
        yawn_freq: float,
        head_drop_freq: float,
        avg_historical_risk: float
    ) -> Dict[str, Any]:
        """
        Executes a prediction using the loaded ensemble models.
        
        Args:
            blink_freq: Number of eye closure events per minute.
            yawn_freq: Number of yawning events per minute.
            head_drop_freq: Number of head tilt violation events per minute.
            avg_historical_risk: Averaged risk score over the active session.
            
        Returns:
            Dictionary containing prediction labels and probability scores.
        """
        if not self.models_loaded:
            return {
                "fatigue_probability": 0.0,
                "prediction_label": "Unknown (Not Trained)",
                "lr_probability": 0.0,
                "rf_probability": 0.0,
                "ready": False
            }
            
        try:
            # 1. Feature Vector format: [Blink, Yawn, Head Drop, Avg Risk]
            feature_vector = np.array([[blink_freq, yawn_freq, head_drop_freq, avg_historical_risk]], dtype=np.float32)
            
            # 2. Scale features
            scaled_features = self.scaler.transform(feature_vector)
            
            # 3. Model predictions (probabilities for class 1 - fatigued)
            prob_lr = float(self.model_lr.predict_proba(scaled_features)[0][1])
            prob_rf = float(self.model_rf.predict_proba(scaled_features)[0][1])
            
            # Ensemble average
            ensemble_prob = (prob_lr + prob_rf) / 2.0
            prediction_label = "Fatigued" if ensemble_prob > 0.5 else "Attentive"
            
            return {
                "fatigue_probability": ensemble_prob,
                "prediction_label": prediction_label,
                "lr_probability": prob_lr,
                "rf_probability": prob_rf,
                "ready": True
            }
        except Exception as e:
            logger.error(f"FatiguePredictor: Prediction execution error: {e}")
            return {
                "fatigue_probability": 0.0,
                "prediction_label": "Error",
                "lr_probability": 0.0,
                "rf_probability": 0.0,
                "ready": False
            }

    def save_weights(self, scaler: Any, model_lr: Any, model_rf: Any):
        """Saves trained model assets to disk."""
        try:
            with open(self.scaler_path, 'wb') as f:
                pickle.dump(scaler, f)
            with open(self.lr_path, 'wb') as f:
                pickle.dump(model_lr, f)
            with open(self.rf_path, 'wb') as f:
                pickle.dump(model_rf, f)
            self.load_models() # reload
            logger.info("FatiguePredictor: Saved and re-cached updated model assets.")
        except Exception as e:
            logger.error(f"FatiguePredictor: Failed to save weights: {e}")
            raise
