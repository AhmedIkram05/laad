"""Tests for RAG calibration module."""

import pytest
import numpy as np
from unittest.mock import MagicMock, patch, mock_open


class TestCalibrationManager:
    """Test cases for CalibrationManager class."""

    def test_initialization(self):
        """Test calibration manager initialization."""
        with patch("builtins.open", mock_open(read_data='{"scale": 1.0, "bias": 0.0, "is_fitted": false}')):
            with patch("backend.src.rag.calibration.Path") as mock_path:
                mock_path.return_value.exists.return_value = False

                from backend.src.rag.calibration import CalibrationManager
                manager = CalibrationManager()

                assert manager.params.scale == 1.0
                assert manager.params.bias == 0.0
                assert manager.params.is_fitted is False

    def test_add_feedback(self):
        """Test adding feedback data."""
        with patch("backend.src.rag.calibration.Path"):
            from backend.src.rag.calibration import CalibrationManager
            import tempfile

            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                f.write('{"scale": 1.0, "bias": 0.0, "is_fitted": false, "sample_size": 0}')
                temp_path = f.name

            with patch("backend.src.rag.calibration.CalibrationManager._get_calibration_file") as mock_file:
                mock_file.return_value = temp_path

                manager = CalibrationManager()
                manager.add_feedback(0.8, True)
                manager.add_feedback(0.6, False)

                assert len(manager.calibration_data) == 2
                assert manager.calibration_data[0] == (0.8, True)
                assert manager.calibration_data[1] == (0.6, False)

    def test_apply_calibration_when_not_fitted(self):
        """Test applying calibration when not fitted."""
        with patch("backend.src.rag.calibration.Path"):
            from backend.src.rag.calibration import CalibrationManager

            manager = CalibrationManager()
            result = manager.apply(0.7)

            assert result.calibrated_confidence == 0.7
            assert result.is_calibrated is False

    def test_apply_calibration_when_fitted(self):
        """Test applying Platt scaling when fitted."""
        from backend.src.rag.calibration import CalibrationManager, CalibrationParams

        manager = CalibrationManager()
        manager.params = CalibrationParams(
            scale=2.0,
            bias=-1.0,
            is_fitted=True,
        )

        result = manager.apply(0.7)

        assert result.is_calibrated is True
        assert 0 <= result.calibrated_confidence <= 1

    def test_get_status(self):
        """Test getting calibration status."""
        from backend.src.rag.calibration import CalibrationManager, CalibrationParams

        manager = CalibrationManager()
        manager.params = CalibrationParams(
            scale=1.5,
            bias=0.2,
            is_fitted=True,
            sample_size=100,
            ece_score=0.05,
        )

        status = manager.get_status()

        assert status["is_calibrated"] is True
        assert status["sample_size"] == 100
        assert status["ece_score"] == 0.05
        assert status["scale"] == 1.5


class TestCalibrationParams:
    """Test cases for CalibrationParams dataclass."""

    def test_params_creation(self):
        """Test CalibrationParams can be created."""
        from backend.src.rag.calibration import CalibrationParams

        params = CalibrationParams(
            scale=1.2,
            bias=0.3,
            is_fitted=True,
            sample_size=50,
            ece_score=0.08,
        )

        assert params.scale == 1.2
        assert params.bias == 0.3
        assert params.is_fitted is True
        assert params.sample_size == 50
        assert params.ece_score == 0.08

    def test_fit_with_sufficient_data(self):
        from backend.src.rag.calibration import CalibrationManager

        with patch("backend.src.rag.calibration.Path"):
            manager = CalibrationManager()
            for i in range(25):
                manager.add_feedback(0.5 + i * 0.02, i % 2 == 0)

            result = manager.fit(min_samples=20)
            assert result.is_calibrated is True
            assert result.calibration_params.is_fitted is True
            assert result.calibration_params.sample_size >= 20

    def test_fit_with_insufficient_data(self):
        from backend.src.rag.calibration import CalibrationManager

        with patch("backend.src.rag.calibration.Path"):
            manager = CalibrationManager()
            manager.add_feedback(0.7, True)

            result = manager.fit(min_samples=20)
            assert result.is_calibrated is False

    def test_maybe_fit_debounce(self):
        from backend.src.rag.calibration import CalibrationManager

        with patch("backend.src.rag.calibration.Path"):
            manager = CalibrationManager()
            for i in range(25):
                manager.add_feedback(0.5 + i * 0.02, i % 2 == 0)

            first = manager.maybe_fit(min_samples=20)
            second = manager.maybe_fit(min_samples=20)

            assert first is True
            assert second is False

    def test_ece_calculation(self):
        from backend.src.rag.calibration import CalibrationManager
        import numpy as np

        with patch("backend.src.rag.calibration.Path"):
            manager = CalibrationManager()
            confidences = np.array([0.5, 0.6, 0.7, 0.8, 0.9])
            correctness = np.array([0, 1, 1, 1, 1])
            ece = manager._calculate_ece(confidences, correctness, 1.0, 0.0)
            assert 0 <= ece <= 1