from __future__ import annotations

import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

import requests
import streamlit as st

import subprocess
import time

from core.catalogs import LLM_MODELS, SHORT_TEMPLATES, TRANSCRIPTION_MODELS
from services.hardware import HardwareSelector

BACKEND_URL = os.getenv("CLIPFORGE_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
DEFAULT_DOWNLOAD_DIR = Path(os.getenv("CLIPFORGE_DOWNLOAD_DIR", tempfile.gettempdir()))


# Função para garantir que o backend está rodando
@st.cache_resource
def iniciar_backend():
    # Inicia o uvicorn em segundo plano (background process)
    # Substitua "api:app" pelo caminho correto do seu arquivo da API
    processo = subprocess.Popen(
        ["uvicorn", "api:app", "--host", "127.0.0.1", "--port", "8000"]
    )
    
    # Aguarda alguns segundos para a API subir completamente antes de liberar o app
    time.sleep(3)
    return processo

# Garante que a API vai rodar uma única vez (graças ao cache_resource)
iniciar_backend()

# Para fazer requisições ao seu backend de dentro do Streamlit, use sempre o IP local:
if st.button("Chamar API"):
    try:
        resposta = requests.get("http://127.0.0")
        st.write(resposta.json())
    except Exception as e:
        st.error(f"Erro ao conectar na API: {e}")

st.set_page_config(page_title="Media Hub AI", layout="wide")

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
    div[data-testid="stHorizontalBlock"] {align-items: stretch;}
    div[data-testid="stMetricValue"] {font-size: 1.2rem;}
    @media (max-width: 760px) {
        .block-container {padding-left: 1rem; padding-right: 1rem;}
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def api_get(path: str) -> dict[str, Any] | None:
    try:
        response = requests.get(f"{BACKEND_URL}{path}", timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException:
        return None


def api_post(path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    try:
        response = requests.post(f"{BACKEND_URL}{path}", json=payload, timeout=900)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as exc:
        detail = ""
        try:
            detail = response.json().get("detail", "")
        except Exception:
            detail = response.text
        st.error(detail or f"Backend request failed: {exc}")
        return None
    except requests.exceptions.RequestException as exc:
        st.error(f"Backend request failed: {exc}")
        return None


def api_upload_file(uploaded_file: Any) -> str | None:
    try:
        files = {
            "file": (
                uploaded_file.name,
                uploaded_file,
                uploaded_file.type or "application/octet-stream",
            )
        }
        response = requests.post(f"{BACKEND_URL}/upload_source", files=files, timeout=900)
        response.raise_for_status()
        return response.json().get("source_path")
    except requests.exceptions.RequestException as exc:
        st.error(f"Falha ao enviar arquivo: {exc}")
        return None


def load_options() -> dict[str, Any]:
    backend_options = api_get("/options")
    if backend_options:
        return backend_options
    return {
        "transcription_models": [asdict(model) for model in TRANSCRIPTION_MODELS],
        "llm_models": [asdict(model) for model in LLM_MODELS],
        "templates": [asdict(template) for template in SHORT_TEMPLATES],
        "execution": {
            "choices": ["auto", "cpu", "gpu"],
            "detected": asdict(HardwareSelector().resolve("auto")),
        },
    }


def model_label(model: dict[str, Any]) -> str:
    return f"{model['provider']} / {model['label']} - {model['location']} - {model['speed']}"


def template_label(template: dict[str, Any]) -> str:
    return f"{template['label']} - {template['recommended_use']}"


if "download_history" not in st.session_state:
    st.session_state.download_history = []

options = load_options()
detected_device = options["execution"]["detected"]

st.title("Media Hub AI")

status = api_get("/health")
if status:
    st.success("Backend conectado")
else:
    st.warning("Backend indisponivel. Execute: uvicorn api:app --host 127.0.0.1 --port 8000")

with st.sidebar:
    st.subheader("Execution")
    st.metric("Device", detected_device["label"])
    if detected_device.get("gpu_name"):
        st.caption(f"GPU: {detected_device['gpu_name']}")
    if detected_device.get("vram_gb"):
        st.caption(f"VRAM: {detected_device['vram_gb']} GB")
    st.caption(f"Estimated speed: {detected_device['estimated_speed']}")

tabs = st.tabs(["Download", "Short Studio", "History"])

with tabs[0]:
    left, right = st.columns([1.1, 0.9])
    with left:
        st.subheader("Download media")
        url = st.text_input(
            "URL",
            placeholder="https://youtube.com/..., https://tiktok.com/..., https://x.com/...",
        )
        platform = st.selectbox("Platform", ["Auto", "YouTube", "Instagram", "TikTok", "X"])
        file_type = st.selectbox("Type", ["Video", "Audio", "Image"], index=0)
        quality = st.selectbox("Quality", ["Best", "1080p", "720p", "480p", "360p"], index=0)
        format_map = {"Video": "mp4", "Audio": "mp3", "Image": "jpg"}
        filename = st.text_input("Custom filename")

        if st.button("Download media", type="primary"):
            if not url.strip():
                st.error("Informe uma URL de midia valida.")
            else:
                payload = {
                    "url": url,
                    "platform": None if platform == "Auto" else platform,
                    "selected_format": file_type,
                    "quality": quality,
                    "file_ext": format_map[file_type],
                    "filename": filename or None,
                }
                with st.spinner("Downloading..."):
                    result = api_post("/download", payload)
                if result:
                    output_path = result.get("output_path", "")
                    st.session_state.download_history.insert(0, output_path)
                    st.success("Download concluido")
                    st.code(output_path)
                    if output_path:
                        file_path = Path(output_path)
                        if file_path.exists() and file_path.is_file():
                            mime = {
                                ".mp4": "video/mp4",
                                ".mov": "video/quicktime",
                                ".webm": "video/webm",
                                ".mp3": "audio/mpeg",
                                ".wav": "audio/wav",
                                ".m4a": "audio/mp4",
                                ".jpg": "image/jpeg",
                                ".jpeg": "image/jpeg",
                                ".png": "image/png",
                                ".webp": "image/webp",
                            }.get(file_path.suffix.lower(), "application/octet-stream")
                            with open(file_path, "rb") as file_obj:
                                file_bytes = file_obj.read()
                            st.download_button(
                                "Salvar no dispositivo",
                                data=file_bytes,
                                file_name=file_path.name,
                                mime=mime,
                            )
    with right:
        st.subheader("Authentication")
        st.write("Cookies are selected automatically by URL.")
        st.write("Supported paths:")
        st.code("cookies/youtube.txt\ncookies/instagram.txt\ncookies/tiktok.txt\ncookies/twitter.txt")
        st.write("JSON exports are converted automatically to Netscape format.")

with tabs[1]:
    left, right = st.columns([1.05, 0.95])
    with left:
        st.subheader("Source")
        uploaded_source = st.file_uploader(
            "Selecione um vídeo do seu dispositivo",
            type=["mp4", "mov", "mkv", "webm", "avi", "m4v"],
            help="Faça upload de um vídeo local para criar shorts diretamente do seu dispositivo.",
        )
        if uploaded_source is not None:
            st.success(f"Arquivo local selecionado: {uploaded_source.name}")
        source = st.text_input(
            "Source URL or server path",
            placeholder="https://youtube.com/... ou caminho do arquivo no servidor",
        )
        preset = st.selectbox(
            "Destination",
            ["youtube_shorts", "tiktok", "instagram_reels", "vertical_feed", "square"],
            format_func=lambda value: {
                "youtube_shorts": "YouTube Shorts - 9:16",
                "tiktok": "TikTok - 9:16",
                "instagram_reels": "Instagram Reels - 9:16",
                "vertical_feed": "Vertical feed - 4:5",
                "square": "Square - 1:1",
            }[value],
        )
        clips_count = st.slider("Clips", 1, 10, 3)
        target_duration = st.slider("Final duration in seconds", 5, 180, 30)
        speed = st.slider("Speed", 0.5, 2.0, 1.0, 0.05)
        filter_preset = st.selectbox(
            "Filter",
            ["vibrant", "cinematic", "warm", "cool", "black_and_white", "none"],
            index=0,
        )

    with right:
        st.subheader("AI")
        transcription_models = options["transcription_models"]
        selected_transcription = st.selectbox(
            "Transcription model",
            transcription_models,
            index=1 if len(transcription_models) > 1 else 0,
            format_func=model_label,
        )
        st.caption(
            
                f"{selected_transcription['description']} "
                f"Capabilities: {selected_transcription['capabilities']}. "
                f"RAM: {selected_transcription['ram']}; VRAM: {selected_transcription['vram']}."
            
        )

        llm_models = options["llm_models"]
        selected_llm = st.selectbox("LLM model", llm_models, format_func=model_label)
        st.caption(f"{selected_llm['description']} This is reserved for upcoming AI scoring workflows.")

        execution_device = st.radio(
            "Execution",
            options["execution"]["choices"],
            horizontal=True,
            format_func=lambda value: {"auto": "Auto", "cpu": "CPU", "gpu": "GPU"}[value],
        )
        language = st.selectbox("Transcription language", ["auto", "pt", "en", "es"], index=0)

    st.subheader("Template gallery")
    template_options = options["templates"]
    selected_template = st.radio(
        "Template",
        template_options,
        horizontal=False,
        format_func=template_label,
    )
    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Aspect", selected_template["aspect_ratio"])
    t2.metric("Webcam", selected_template["webcam_position"])
    t3.metric("Subtitles", selected_template["subtitle_style"])
    t4.metric("Mode", selected_template["label"])
    st.caption(selected_template["description"])

    captions_enabled = st.checkbox("Captions", value=True)
    caption_preset = st.selectbox("Caption style", ["viral", "clean", "neon", "minimal"], index=0)
    caption_font = st.text_input("Caption font", value="Arial")

    if st.button("Create shorts", type="primary"):
        source_path = source
        if uploaded_source is not None:
            with st.spinner("Enviando vídeo local..."):
                uploaded_path = api_upload_file(uploaded_source)
            if uploaded_path:
                source_path = uploaded_path
            else:
                source_path = ""

        if not source_path:
            st.error("Informe um link ou selecione um vídeo local para criar shorts.")
        else:
            payload = {
                "source": source_path,
                "output_dir": str(DEFAULT_DOWNLOAD_DIR / "shorts"),
                "preset": preset,
                "clips_count": clips_count,
                "target_duration": target_duration,
                "speed": speed,
                "mirror": False,
                "filter_preset": filter_preset,
                "template": selected_template["id"],
                "captions_enabled": captions_enabled,
                "caption_preset": caption_preset,
                "caption_font": caption_font,
                "language": None if language == "auto" else language,
                "whisper_model": selected_transcription["id"],
                "execution_device": execution_device,
            }
            with st.spinner("Rendering shorts..."):
                result = api_post("/shorts", payload)
            if result:
                st.success("Short criado")
                for path in result.get("outputs", []):
                    st.code(path)
                    file_path = Path(path)
                    if file_path.exists() and file_path.is_file():
                        mime = {
                            ".mp4": "video/mp4",
                            ".mov": "video/quicktime",
                            ".webm": "video/webm",
                        }.get(file_path.suffix.lower(), "application/octet-stream")
                        with open(file_path, "rb") as file_obj:
                            file_bytes = file_obj.read()
                        st.download_button(
                            f"Baixar {file_path.name}",
                            data=file_bytes,
                            file_name=file_path.name,
                            mime=mime,
                        )
                for warning in result.get("warnings", []):
                    st.warning(warning)

with tabs[2]:
    st.subheader("Download history")
    if not st.session_state.download_history:
        st.info("No downloads in this session yet.")
    for item in st.session_state.download_history:
        st.code(item)
