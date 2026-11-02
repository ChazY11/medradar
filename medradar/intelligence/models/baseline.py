"""Deterministic, dependency-free logistic baseline with train-only imputation."""
from __future__ import annotations

import math
from typing import Any, Iterable


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    if not n:
        return 0.0
    return ordered[n // 2] if n % 2 else 0.5 * (ordered[n // 2 - 1] + ordered[n // 2])


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-min(value, 700))
        return 1.0 / (1.0 + z)
    z = math.exp(max(value, -700))
    return z / (1.0 + z)


class LogisticBaseline:
    def __init__(self, feature_names: Iterable[str], *, epochs: int = 180,
                 learning_rate: float = 0.15, l2: float = 1.0) -> None:
        self.feature_names = list(feature_names)
        self.epochs = epochs
        self.learning_rate = learning_rate
        self.l2 = l2
        self.medians: dict[str, float] = {}
        self.means: list[float] = []
        self.scales: list[float] = []
        self.weights: list[float] = []
        self.intercept = 0.0
        self.missing_features: list[str] = []

    def _raw(self, row: dict[str, Any], name: str) -> float:
        value = row.get(name)
        if value is None:
            return self.medians.get(name, 0.0)
        try:
            value = float(value)
            return value if math.isfinite(value) else self.medians.get(name, 0.0)
        except (TypeError, ValueError):
            return self.medians.get(name, 0.0)

    def _design(self, rows: list[dict[str, Any]], fit: bool = False) -> list[list[float]]:
        base = [[self._raw(row, name) for name in self.feature_names] for row in rows]
        if fit:
            self.means = [sum(row[j] for row in base) / len(base) for j in range(len(self.feature_names))]
            self.scales = []
            for j, mean in enumerate(self.means):
                variance = sum((row[j] - mean) ** 2 for row in base) / len(base)
                self.scales.append(max(math.sqrt(variance), 1e-6))
        design = [[(row[j] - self.means[j]) / self.scales[j] for j in range(len(row))] for row in base]
        for row, source in zip(design, rows):
            row.extend(1.0 if source.get(name) is None else 0.0 for name in self.missing_features)
        return design

    def fit(self, rows: list[dict[str, Any]], labels: list[int]) -> "LogisticBaseline":
        if len(rows) != len(labels) or not rows:
            raise ValueError("training rows and labels must be non-empty and aligned")
        for name in self.feature_names:
            observed = [float(row[name]) for row in rows if row.get(name) is not None and math.isfinite(float(row[name]))]
            self.medians[name] = _median(observed)
        self.missing_features = [name for name in self.feature_names if any(row.get(name) is None for row in rows)]
        x = self._design(rows, fit=True)
        width = len(x[0])
        self.weights = [0.0] * width
        prevalence = min(max(sum(labels) / len(labels), 1e-5), 1 - 1e-5)
        self.intercept = math.log(prevalence / (1 - prevalence))
        n = len(rows)
        for _ in range(self.epochs):
            gradients = [0.0] * width
            intercept_gradient = 0.0
            for row, label in zip(x, labels):
                linear = self.intercept + sum(w * value for w, value in zip(self.weights, row))
                error = _sigmoid(linear) - label
                intercept_gradient += error
                for j, value in enumerate(row):
                    gradients[j] += error * value
            self.intercept -= self.learning_rate * intercept_gradient / n
            for j in range(width):
                penalty = self.l2 * self.weights[j] / n
                self.weights[j] -= self.learning_rate * (gradients[j] / n + penalty)
        return self

    def predict_proba(self, rows: list[dict[str, Any]]) -> list[float]:
        if not rows:
            return []
        if not self.weights:
            raise ValueError("model is not fitted")
        x = self._design(rows)
        return [_sigmoid(self.intercept + sum(w * value for w, value in zip(self.weights, row))) for row in x]

    def contributions(self, row: dict[str, Any]) -> list[dict[str, Any]]:
        """Per-feature evidence with explicit raw and standardized scales.

        ``contribution`` is ``coefficient * standardized_value``, i.e. per one
        training-standard-deviation change, not per raw unit. ``value`` is kept
        as an alias of ``raw_value`` for backward compatibility; a null raw
        value means the training median was imputed and ``median_imputed`` is
        true (such a row still has a nonzero ``standardized_value`` and
        ``contribution``).
        """
        design = self._design([row])[0]
        values = []
        for j, name in enumerate(self.feature_names):
            raw = row.get(name)
            values.append({
                "feature": name, "contribution": self.weights[j] * design[j],
                "value": raw, "raw_value": raw, "standardized_value": design[j],
                "median_imputed": self._imputed(row, name),
                "coefficient": self.weights[j],
            })
        return sorted(values, key=lambda item: abs(item["contribution"]), reverse=True)

    def _imputed(self, row: dict[str, Any], name: str) -> bool:
        value = row.get(name)
        if value is None:
            return True
        try:
            return not math.isfinite(float(value))
        except (TypeError, ValueError):
            return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm": "logistic_regression_batch_gd", "features": self.feature_names,
            "epochs": self.epochs, "learning_rate": self.learning_rate, "l2": self.l2,
            "medians": self.medians, "means": self.means, "scales": self.scales,
            "missing_features": self.missing_features, "weights": self.weights,
            "intercept": self.intercept,
        }
