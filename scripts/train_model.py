'Training a random forest classifier on training data to predict fire risks.'

import joblib
import pandas as pd
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    classification_report, confusion_matrix, roc_auc_score
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

# Use lagged dataset if available, otherwise fall back to base dataset
LAGGED_PATH = Path("data/training_dataset_lagged.csv")
BASE_PATH   = Path("data/training_dataset.csv")
DATA_PATH   = LAGGED_PATH if LAGGED_PATH.exists() else BASE_PATH

MODEL_DIR  = Path("models")
MODEL_PATH = MODEL_DIR / "fire_risk_model.pkl"

BASE_FEATURES = [
    "temperature", "humidity", "wind_speed", "precipitation",
    "station_lat", "station_lon", "day_of_year", "month",
]
LAGGED_FEATURES = ["days_since_rain", "temp_rolling_7d"]
LABEL = "fire"


def main() -> None:
    MODEL_DIR.mkdir(exist_ok=True)

    print(f"Loading dataset from {DATA_PATH}...")
    df = pd.read_csv(DATA_PATH, parse_dates=["date"])
    df["day_of_year"] = df["date"].dt.dayofyear
    df["month"]       = df["date"].dt.month
    print(f"  {len(df)} rows, {df[LABEL].sum()} fire / {(df[LABEL]==0).sum()} non-fire")

    # Include lagged features only if they exist in this dataset
    extra = [f for f in LAGGED_FEATURES if f in df.columns]
    features = BASE_FEATURES + extra
    if extra:
        print(f"  Lagged features included: {extra}")
        for f in extra:
            pct = df[f].notna().mean() * 100
            print(f"    {f}: {pct:.1f}% populated")
    else:
        print("  No lagged features found — training on base 8 features")

    X = df[features]
    y = df[LABEL]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"  Train: {len(X_train)}  Test: {len(X_test)}")

    pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("clf", RandomForestClassifier(
            n_estimators=300,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )),
    ])

    print("\nTraining Random Forest...")
    pipeline.fit(X_train, y_train)

    y_pred  = pipeline.predict(X_test)
    y_proba = pipeline.predict_proba(X_test)[:, 1]

    print("\n-- Evaluation --")
    print(classification_report(y_test, y_pred, target_names=["non-fire", "fire"]))
    print("Confusion matrix (rows=actual, cols=predicted):")
    print(confusion_matrix(y_test, y_pred))
    print(f"\nROC-AUC: {roc_auc_score(y_test, y_proba):.4f}")

    print("\nFeature importances:")
    importances = pipeline.named_steps["clf"].feature_importances_
    for feat, imp in sorted(zip(features, importances), key=lambda x: -x[1]):
        print(f"  {feat:<20} {imp:.4f}")

    joblib.dump(pipeline, MODEL_PATH)
    print(f"\nModel saved -> {MODEL_PATH}")
    print(f"Features used: {features}")


if __name__ == "__main__":
    main()
