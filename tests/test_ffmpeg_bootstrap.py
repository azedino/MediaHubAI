from pathlib import Path

from services import ffmpeg as ffmpeg_module


def test_resolve_ffmpeg_executable_uses_imageio_binary(monkeypatch, tmp_path):
    fake_binary = tmp_path / "ffmpeg"
    fake_binary.write_text("placeholder")
    fake_binary.chmod(0o755)

    monkeypatch.setattr(ffmpeg_module.shutil, "which", lambda _: None)
    monkeypatch.setattr(ffmpeg_module, "get_ffmpeg_exe", lambda: str(fake_binary))
    monkeypatch.delenv("CLIPFORGE_FFMPEG", raising=False)

    resolved = ffmpeg_module.resolve_ffmpeg_executable()

    assert resolved == fake_binary.resolve()
