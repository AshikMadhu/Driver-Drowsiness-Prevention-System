import sys
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
from pathlib import Path
from typing import Optional

# Add root folder to python path to resolve imports
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

from src.ml_engine.fatigue_predictor import FatiguePredictor
from src.utils.logger import logger

def generate_synthetic_fatigue_dataset(num_samples: int = 1200) -> tuple:
    """
    Synthesizes a driver fatigue telemetry dataset for model calibration.
    Features: [Blink Frequency, Yawn Frequency, Head Drop Frequency, Avg Risk Score]
    """
    logger.info(f"Generating synthetic training dataset ({num_samples} samples)...")
    np.random.seed(42)
    
    half_samples = num_samples // 2
    
    # 1. Attentive Class (y = 0)
    # Ratios representing standard alert driving profiles
    blink_active = np.random.normal(loc=2.2, scale=1.0, size=half_samples)
    yawn_active = np.random.normal(loc=0.1, scale=0.15, size=half_samples)
    headdrop_active = np.random.normal(loc=0.2, scale=0.3, size=half_samples)
    risk_active = np.random.normal(loc=0.6, scale=0.4, size=half_samples)
    y_active = np.zeros(half_samples, dtype=np.int32)
    
    # 2. Fatigued Class (y = 1)
    # Ratios representing fatigued driving profiles
    blink_fatigue = np.random.normal(loc=11.5, scale=2.8, size=half_samples)
    yawn_fatigue = np.random.normal(loc=2.4, scale=0.9, size=half_samples)
    headdrop_fatigue = np.random.normal(loc=3.2, scale=1.2, size=half_samples)
    risk_fatigue = np.random.normal(loc=4.1, scale=1.1, size=half_samples)
    y_fatigue = np.ones(half_samples, dtype=np.int32)
    
    # Concatenate classes
    blink = np.concatenate([blink_active, blink_fatigue])
    yawn = np.concatenate([yawn_active, yawn_fatigue])
    headdrop = np.concatenate([headdrop_active, headdrop_fatigue])
    risk = np.concatenate([risk_active, risk_fatigue])
    y = np.concatenate([y_active, y_fatigue])
    
    # Ensure all frequencies remain >= 0
    blink = np.clip(blink, 0.0, None)
    yawn = np.clip(yawn, 0.0, None)
    headdrop = np.clip(headdrop, 0.0, None)
    risk = np.clip(risk, 0.0, None)
    
    # Feature matrix X: columns correspond to [Blink, Yawn, Head Drop, Avg Risk]
    X = np.stack([blink, yawn, headdrop, risk], axis=1)
    
    # Shuffle dataset
    shuffled_indices = np.random.permutation(num_samples)
    X = X[shuffled_indices]
    y = y[shuffled_indices]
    
    return X, y

def train_and_evaluate_fatigue_models(model_dir: Optional[Path] = None):
    print("=" * 60)
    print("      DRIVER FATIGUE PREDICTOR MODEL TRAINING PIPELINE    ")
    print("=" * 60)
    
    # 1. Load Data
    X, y = generate_synthetic_fatigue_dataset(num_samples=1000)
    
    # 2. Split Data
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    logger.info(f"Splitting dataset: Train shape: {X_train.shape} | Test shape: {X_test.shape}")
    
    # 3. Standardize Features
    logger.info("Scaling features using StandardScaler...")
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    # 4. Train Models
    # Model A: Logistic Regression (interpretable, baseline)
    logger.info("Training Logistic Regression Model...")
    model_lr = LogisticRegression(C=1.0, random_state=42)
    model_lr.fit(X_train_scaled, y_train)
    
    # Model B: Random Forest Classifier (non-linear, ensemble)
    logger.info("Training Random Forest Classifier...")
    model_rf = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)
    model_rf.fit(X_train_scaled, y_train)
    
    # 5. Evaluate Models
    print("\n" + "-" * 50)
    print("    EVALUATION METRICS SUMMARY    ")
    print("-" * 50)
    
    models = [("Logistic Regression", model_lr), ("Random Forest", model_rf)]
    feature_names = ["Blink Frequency", "Yawn Frequency", "Head Drop Frequency", "Avg Historical Risk"]
    
    for name, model in models:
        y_pred = model.predict(X_test_scaled)
        y_prob = model.predict_proba(X_test_scaled)[:, 1]
        
        acc = accuracy_score(y_test, y_pred)
        prec = precision_score(y_test, y_pred)
        rec = recall_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred)
        auc = roc_auc_score(y_test, y_prob)
        
        print(f"\n{name} Results:")
        print(f"  - Accuracy:  {acc * 100:.2f}%")
        print(f"  - Precision: {prec * 100:.2f}%")
        print(f"  - Recall:    {rec * 100:.2f}%")
        print(f"  - F1-Score:  {f1:.4f}")
        print(f"  - ROC-AUC:   {auc:.4f}")
        
        # Display coefficients / importances for academic analysis
        if name == "Logistic Regression":
            print("  Feature Coefficients:")
            for feat, coef in zip(feature_names, model.coef_[0]):
                print(f"    * {feat}: {coef:.4f}")
        elif name == "Random Forest":
            print("  Feature Importances:")
            for feat, imp in zip(feature_names, model.feature_importances_):
                print(f"    * {feat}: {imp * 100:.2f}%")
 
    print("-" * 50 + "\n")
    
    # 6. Save Model weights
    predictor = FatiguePredictor(model_dir=model_dir) if model_dir else FatiguePredictor()
    predictor.save_weights(scaler, model_lr, model_rf)
    
    print("=" * 60)
    print("     TRAINING COMPLETED: Model weights successfully saved.    ")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    train_and_evaluate_fatigue_models()
