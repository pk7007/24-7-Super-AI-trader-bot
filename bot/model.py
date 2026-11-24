"""LightGBM 3-class signal model: P(down), P(flat), P(up)."""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier

from .features import FEATURE_COLUMNS

PROB_COLUMNS = ["p_down", "p_flat", "p_up"]


class SignalModel:
    def __init__(self, seed: int = 7):
        self.clf = LGBMClassifier(
            objective="multiclass",
            n_estimators=250,
            learning_rate=0.03,
            num_leaves=15,
            min_child_samples=200,
            subsample=0.7,
            subsample_freq=1,
            colsample_bytree=0.7,
            reg_lambda=5.0,
            random_state=seed,
            verbose=-1,
            n_jobs=2,
        )
        self.fitted = False

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "SignalModel":
        mask = X.notna().all(axis=1) & y.notna()
        self.clf.fit(X.loc[mask, FEATURE_COLUMNS], y[mask].astype(int))
        self.fitted = True
        return self

    def predict_proba(self, X: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame(np.nan, index=X.index, columns=PROB_COLUMNS)
        mask = X[FEATURE_COLUMNS].notna().all(axis=1)
        if mask.any():
            p = self.clf.predict_proba(X.loc[mask, FEATURE_COLUMNS])
            full = np.zeros((p.shape[0], 3))
            for j, cls in enumerate(self.clf.classes_):
                full[:, int(cls)] = p[:, j]
            out.loc[mask, PROB_COLUMNS] = full
        return out

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.clf, path)

    @classmethod
    def load(cls, path: Path) -> "SignalModel":
        m = cls()
        m.clf = joblib.load(path)
        m.fitted = True
        return m
