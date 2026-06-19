"""Tests for listener utility functions (audio conversion and RMS energy)."""
import struct

import numpy as np


def _audio_int16_to_float32(raw: bytes) -> np.ndarray:
    """Replicate listener's conversion function to avoid importing pyaudio/pvporcupine."""
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    if samples.size == 0:
        return samples
    return samples / 32768.0


def _rms_energy(audio: np.ndarray) -> float:
    """Replicate listener's RMS energy function."""
    if audio.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(audio), dtype=np.float64)))


class TestAudioInt16ToFloat32:
    """Tests for int16 PCM to float32 conversion."""

    def test_audio_int16_to_float32_known(self):
        """Known int16 values should map to expected float32 range."""
        # Pack some known int16 values
        raw = struct.pack("<3h", 0, 16384, -16384)
        result = _audio_int16_to_float32(raw)
        assert len(result) == 3
        assert abs(result[0] - 0.0) < 1e-6
        assert abs(result[1] - 0.5) < 1e-3
        assert abs(result[2] - (-0.5)) < 1e-3

    def test_audio_int16_to_float32_empty(self):
        """Empty bytes should return empty array."""
        result = _audio_int16_to_float32(b"")
        assert result.size == 0

    def test_audio_int16_to_float32_range(self):
        """All output values should be in [-1, 1]."""
        # Full range int16 values
        raw = struct.pack("<2h", -32768, 32767)
        result = _audio_int16_to_float32(raw)
        assert all(-1.0 <= v <= 1.0 for v in result)

    def test_audio_int16_to_float32_max(self):
        """Max int16 (32767) should map close to 1.0."""
        raw = struct.pack("<h", 32767)
        result = _audio_int16_to_float32(raw)
        assert abs(result[0] - 1.0) < 0.001

    def test_audio_int16_to_float32_min(self):
        """Min int16 (-32768) should map to -1.0."""
        raw = struct.pack("<h", -32768)
        result = _audio_int16_to_float32(raw)
        assert abs(result[0] - (-1.0)) < 0.001


class TestRmsEnergy:
    """Tests for RMS energy calculation."""

    def test_rms_energy_silence(self):
        """All-zero signal should have 0.0 RMS."""
        audio = np.zeros(100, dtype=np.float32)
        assert _rms_energy(audio) == 0.0

    def test_rms_energy_full_scale(self):
        """Known constant signal should have predictable RMS."""
        # Constant signal of 0.5 -> RMS = 0.5
        audio = np.full(100, 0.5, dtype=np.float32)
        rms = _rms_energy(audio)
        assert abs(rms - 0.5) < 1e-6

    def test_rms_energy_empty(self):
        """Empty array should return 0.0."""
        audio = np.array([], dtype=np.float32)
        assert _rms_energy(audio) == 0.0

    def test_rms_energy_sine_wave(self):
        """Sine wave RMS should be approximately 1/sqrt(2) of amplitude."""
        t = np.linspace(0, 2 * np.pi, 10000, dtype=np.float32)
        audio = np.sin(t)
        rms = _rms_energy(audio)
        # RMS of a sine wave ≈ 1/sqrt(2) ≈ 0.7071
        assert abs(rms - 0.7071) < 0.01

    def test_rms_energy_positive(self):
        """RMS energy should always be non-negative."""
        audio = np.array([-0.5, -0.3, -0.1], dtype=np.float32)
        assert _rms_energy(audio) > 0.0
