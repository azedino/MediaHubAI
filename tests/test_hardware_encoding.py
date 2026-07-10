from services.ffmpeg import EncoderProfile, FFmpegService
from services.hardware import HardwareSelector


def test_gpu_name_classification_detects_amd_rx() -> None:
    vendor, backend = HardwareSelector._classify_gpu("AMD Radeon RX 6600M")
    assert vendor == "amd"
    assert backend == "amf"


def test_amd_encoder_candidates_prioritize_amf() -> None:
    candidates = FFmpegService._encoder_candidates("amd", "gpu", "")
    assert candidates[0].name == "h264_amf"
    assert candidates[-1].name == "libx264"


def test_cpu_encoder_candidates_skip_gpu_encoders() -> None:
    candidates = FFmpegService._encoder_candidates("amd", "cpu", "")
    assert candidates == (EncoderProfile("libx264", ("-preset", "veryfast", "-crf", "18"), "cpu", False),)
