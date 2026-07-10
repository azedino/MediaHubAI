# Shorts Pipeline Analysis

## Current Weaknesses

- Webcam crops were derived from a median face box. A face is not the webcam region, so hats, shoulders, borders, chair movement, and off-center framing caused wrong ROI and unstable composition.
- Detection sampled only a few frames and did not track temporally. Any bad sample could shift the crop, and there was no confidence validation after the initial choice.
- The FFmpeg layout mixed gameplay, face crop, subtitles, color, speed, and audio in one monolithic method. That made it difficult to test the behavior or replace one stage safely.
- Reaction templates overlaid a small webcam in corners. For gaming/commentary shorts this often covers HUD elements and leaves subtitles competing with gameplay.
- Captions were aligned to the bottom of the full video instead of a reserved safe region. Large viral subtitles could cover HUD or important action.
- Output FPS was forced with `-r 30`, which can duplicate/drop frames depending on source cadence.
- Encoding always used software x264 even when FFmpeg exposes hardware H.264 encoders.

## Redesign

- `video_loader.py` owns metadata loading.
- `scene_detector.py` owns FFmpeg scene rhythm detection.
- `webcam_detector.py` detects a picture-in-picture webcam panel first, using rectangular panel candidates and face-seeded panel candidates. It never renders from a raw face crop.
- `tracker.py` adds OpenCV tracking plus EMA smoothing and hysteresis to prevent teleporting or jitter.
- `layout_engine.py` builds a fixed 1080x1920 composition with top webcam, middle gameplay, and bottom caption safe zone.
- `renderer.py` owns FFmpeg filter graph and encoding arguments, including hardware encoder preference.
- `short_pipeline.py` orchestrates the complete workflow and keeps `ShortCreationService` as a stable public facade.
- `hardware.py` detects NVIDIA, AMD, Intel, or CPU execution. FFmpeg rendering prefers NVENC, AMF, or Quick Sync according to the detected GPU and validates the encoder before use.

## Why This Fixes The Visual Defects

- Webcam framing is frozen from a stable panel ROI, not recomputed from faces per render.
- Tracking/smoothing validates the ROI across sampled time and filters transient detections.
- Gameplay is fit into the middle region with aspect ratio preserved, avoiding stretch and accidental important-content crops.
- Captions render in the reserved lower band with word timing, line wrapping, high contrast, and animated entry.
- Rendering stays in FFmpeg, streams from source media, and avoids loading the full video into memory.
- AMD GPUs such as RX 6600M use `h264_amf` for video encoding instead of accidentally selecting `h264_nvenc`. If any GPU encoder fails at runtime, rendering retries with `libx264`.
- Local transcription uses CUDA when an NVIDIA CUDA stack is available; AMD/Intel machines fall back to CPU transcription while still using GPU video encoding when supported.
