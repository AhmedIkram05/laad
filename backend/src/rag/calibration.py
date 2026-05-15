"""Uncertainty calibration using Platt scaling."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np
from scipy.special import expit

logger = logging.getLogger(__name__)


@dataclass
class CalibrationParams:
    """Calibration parameters for Platt scaling."""
    scale: float = 1.0
    bias: float = 0.0
    is_fitted: bool = False
    sample_size: int = 0
    ece_score: Optional[float] = None


@dataclass
class CalibrationResult:
    """Result of calibration application."""
    calibrated_confidence: float
    is_calibrated: bool
    calibration_params: CalibrationParams


class CalibrationManager:
    """Manages uncertainty calibration using Platt scaling."""

    def __init__(self):
        self.params = self._load_params()
        self.calibration_data: list[tuple[float, bool]] = []
        self._fit_called = False

    def _get_calibration_file(self) -> Path:
        """Get path to calibration parameters file."""
        return Path(__file__).parent / "calibration_params.json"

    def _load_params(self) -> CalibrationParams:
        """Load calibration parameters from file."""
        calibration_file = self._get_calibration_file()
        file_path = Path(calibration_file) if isinstance(calibration_file, str) else calibration_file
        if file_path.exists():
            try:
                with open(file_path, "r") as f:
                    data = json.load(f)
                return CalibrationParams(
                    scale=data.get("scale", 1.0),
                    bias=data.get("bias", 0.0),
                    is_fitted=data.get("is_fitted", False),
                    sample_size=data.get("sample_size", 0),
                    ece_score=data.get("ece_score"),
                )
            except Exception as e:
                logger.warning(f"Failed to load calibration params: {e}")

        return CalibrationParams()

    def _save_params(self) -> None:
        """Save calibration parameters to file."""
        calibration_file = self._get_calibration_file()
        try:
            with open(calibration_file, "w") as f:
                json.dump({
                    "scale": self.params.scale,
                    "bias": self.params.bias,
                    "is_fitted": self.params.is_fitted,
                    "sample_size": self.params.sample_size,
                    "ece_score": self.params.ece_score,
                }, f)
            logger.info("Calibration params saved")
        except Exception as e:
            logger.error(f"Failed to save calibration params: {e}")

    def add_feedback(self, raw_confidence: float, is_correct: bool) -> None:
        """Add user feedback for calibration."""
        self.calibration_data.append((raw_confidence, is_correct))
        logger.debug(f"Added feedback: conf={raw_confidence}, correct={is_correct}")

    def maybe_fit(self, min_samples: int = 20) -> bool:
        """Fit Platt scaling if enough new data accumulated and not already fitted this batch."""
        if self._fit_called:
            return False
        if len(self.calibration_data) < min_samples:
            return False
        self._fit_called = True
        result = self.fit(min_samples=min_samples)
        return result.is_calibrated

    def fit(self, min_samples: int = 20) -> CalibrationResult:
        """Fit Platt scaling on collected feedback."""
        if len(self.calibration_data) < min_samples:
            return CalibrationResult(
                calibrated_confidence=0.5,
                is_calibrated=False,
                calibration_params=self.params,
            )

        confidences = np.array([c for c, _ in self.calibration_data])
        correctness = np.array([1 if is_corr else 0 for _, is_corr in self.calibration_data])

        try:
            from scipy.optimize import minimize

            def loss(params):
                scale, bias = params
                logits = scale * confidences + bias
                probs = expit(logits)
                return np.mean((probs - correctness) ** 2)

            result = minimize(loss, [1.0, 0.0], method="Nelder-Mead")
            scale, bias = result.x

            self.params = CalibrationParams(
                scale=float(scale),
                bias=float(bias),
                is_fitted=True,
                sample_size=len(self.calibration_data),
                ece_score=self._calculate_ece(confidences, correctness, scale, bias),
            )

            self._save_params()
            logger.info(f"Calibration fitted: scale={scale:.3f}, bias={bias:.3f}, ECE={self.params.ece_score:.3f}")

            return CalibrationResult(
                calibrated_confidence=0.5,
                is_calibrated=True,
                calibration_params=self.params,
            )

        except Exception as e:
            logger.error(f"Calibration fitting failed: {e}")
            return CalibrationResult(
                calibrated_confidence=0.5,
                is_calibrated=False,
                calibration_params=self.params,
            )

    def _calculate_ece(
        self,
        confidences: np.ndarray,
        correctness: np.ndarray,
        scale: float,
        bias: float,
    ) -> float:
        """Calculate Expected Calibration Error."""
        n_bins = 5
        bin_boundaries = np.linspace(0, 1, n_bins +1)
        ece = 0.0

        for i in range(n_bins):
            bin_mask = (confidences >= bin_boundaries[i]) & (confidences < bin_boundaries[i + 1])
            bin_size = np.sum(bin_mask)

            if bin_size == 0:
                continue

            bin_conf = confidences[bin_mask]
            bin_corr = correctness[bin_mask]

            avg_confidence = np.mean(bin_conf)
            avg_correctness = np.mean(bin_corr)

            ece += (bin_size / len(confidences)) * abs(avg_confidence - avg_correctness)

        return float(ece)

    def apply(self, raw_confidence: float) -> CalibrationResult:
        """Apply calibration to a raw confidence score."""
        if not self.params.is_fitted:
            return CalibrationResult(
                calibrated_confidence=raw_confidence,
                is_calibrated=False,
                calibration_params=self.params,
            )

        try:
            calibrated = expit(self.params.scale * raw_confidence + self.params.bias)
            calibrated = max(0.0, min(1.0, calibrated))

            return CalibrationResult(
                calibrated_confidence=round(calibrated, 3),
                is_calibrated=True,
                calibration_params=self.params,
            )
        except Exception as e:
            logger.error(f"Calibration application failed: {e}")
            return CalibrationResult(
                calibrated_confidence=raw_confidence,
                is_calibrated=False,
                calibration_params=self.params,
            )

    def get_status(self) -> dict[str, Any]:
        """Get calibration status."""
        return {
            "is_calibrated": self.params.is_fitted,
            "sample_size": self.params.sample_size,
            "ece_score": self.params.ece_score,
            "scale": self.params.scale,
            "bias": self.params.bias,
        }

    def reset(self) -> None:
        """Reset calibration parameters."""
        self.params = CalibrationParams()
        self.calibration_data = []
        self._save_params()
        logger.info("Calibration reset")


_calibration_manager: Optional[CalibrationManager] = None


def get_calibration_manager() -> CalibrationManager:
    """Get singleton calibration manager instance."""
    global _calibration_manager
    if _calibration_manager is None:
        _calibration_manager = CalibrationManager()
    return _calibration_manager