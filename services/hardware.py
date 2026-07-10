from __future__ import annotations

import os
import platform
import re
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GpuInfo:
    name: str
    vendor: str
    backend: str
    vram_gb: float | None = None


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    requested: str
    device: str
    label: str
    gpu_name: str | None
    vram_gb: float | None
    estimated_speed: str
    fallback_reason: str | None = None


class HardwareSelector:
    VALID_CHOICES = ("auto", "cpu", "gpu")

    def resolve(self, requested: str = "auto") -> DeviceInfo:
        requested = (requested or "auto").strip().lower()
        if requested not in self.VALID_CHOICES:
            requested = "auto"

        if requested == "cpu":
            return self._cpu_device(requested)

        gpu = self.preferred_gpu()
        if requested in {"auto", "gpu"} and gpu:
            labels = {
                "nvidia": "GPU (NVIDIA CUDA/NVENC)",
                "amd": "GPU (AMD AMF)",
                "intel": "GPU (Intel Quick Sync)",
            }
            speeds = {"nvidia": "High", "amd": "High", "intel": "Medium"}
            return DeviceInfo(
                requested,
                gpu.backend,
                labels.get(gpu.vendor, "GPU"),
                gpu.name,
                gpu.vram_gb,
                speeds.get(gpu.vendor, "Variable"),
            )

        fallback = None
        if requested == "gpu":
            fallback = "GPU acceleration is unavailable; CPU will be used."
        return self._cpu_device(requested, fallback)

    def preferred_gpu(self) -> GpuInfo | None:
        override = os.environ.get("CLIPFORGE_GPU_VENDOR", "").strip().lower()
        gpus = self.detect_gpus()
        if override:
            for gpu in gpus:
                if gpu.vendor == override:
                    return gpu
        priority = {"nvidia": 0, "amd": 1, "intel": 2}
        return min(gpus, key=lambda gpu: priority.get(gpu.vendor, 99), default=None)

    def detect_gpus(self) -> list[GpuInfo]:
        found: list[GpuInfo] = []
        cuda = self._cuda_info()
        if cuda:
            name, vram = cuda
            found.append(GpuInfo(name, "nvidia", "cuda", vram))

        for name, vram in self._system_video_controllers():
            vendor, backend = self._classify_gpu(name)
            if vendor == "unknown":
                continue
            if any(existing.name.lower() == name.lower() for existing in found):
                continue
            found.append(GpuInfo(name, vendor, backend, vram))
        return found

    @staticmethod
    def _cpu_device(requested: str, fallback: str | None = None) -> DeviceInfo:
        return DeviceInfo(
            requested,
            "cpu",
            "CPU",
            platform.processor() or platform.machine() or "CPU",
            None,
            "Standard",
            fallback,
        )

    @staticmethod
    def _cuda_info() -> tuple[str, float | None] | None:
        try:
            import torch
        except ImportError:
            return None
        if not torch.cuda.is_available():
            return None
        device_index = torch.cuda.current_device()
        props = torch.cuda.get_device_properties(device_index)
        vram = round(float(props.total_memory) / (1024**3), 1) if props.total_memory else None
        return torch.cuda.get_device_name(device_index), vram

    @staticmethod
    def _system_video_controllers() -> list[tuple[str, float | None]]:
        if platform.system().lower() != "windows":
            return []
        command = [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "Get-CimInstance Win32_VideoController | "
                "Select-Object -ExpandProperty Name"
            ),
        ]
        try:
            completed = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=4,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired):
            return []
        names = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
        return [(name, HardwareSelector._estimate_vram_from_name(name)) for name in names]

    @staticmethod
    def _classify_gpu(name: str) -> tuple[str, str]:
        normalized = name.lower()
        if "nvidia" in normalized or "geforce" in normalized or "quadro" in normalized or "rtx" in normalized:
            return "nvidia", "cuda"
        if "amd" in normalized or "radeon" in normalized or re.search(r"\brx\s*\d", normalized):
            return "amd", "amf"
        if "intel" in normalized or "iris" in normalized or "uhd graphics" in normalized:
            return "intel", "qsv"
        return "unknown", "cpu"

    @staticmethod
    def _estimate_vram_from_name(name: str) -> float | None:
        match = re.search(r"(\d+)\s*gb", name.lower())
        return float(match.group(1)) if match else None
