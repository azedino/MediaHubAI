# ClipForge Local

Aplicativo desktop para baixar mídia e transformar vídeos longos em cortes verticais prontos para YouTube Shorts, TikTok e Instagram Reels. A análise editorial, a transcrição, a detecção de câmera de reação e a renderização acontecem localmente.

## O que já funciona

- Download de vídeo, áudio ou imagem via `yt-dlp`, com progresso e pós-processamento por FFmpeg.
- Entrada por link ou arquivo local para a criação de shorts.
- Saídas 9:16 (1080×1920), 4:5 (1080×1350) e 1:1 (1080×1080).
- Legendas automáticas locais com `faster-whisper`, timestamps por palavra e quatro estilos ASS.
- Ranking explicável dos cortes por gancho, curiosidade, emoção, ritmo de fala e mudanças de cena.
- Detecção opcional de câmera de reação com OpenCV e templates de reação no topo, embaixo ou tela dividida.
- Controle de velocidade de 0,5× a 2×, espelhamento, normalização de áudio e filtros de cor.
- Fundo desfocado, preenchimento inteligente, cancelamento e nomes de saída sem sobrescrever arquivos.
- Fallback determinístico: sem IA instalada, o app ainda cria cortes distribuídos no tempo.

> O “score de potencial” é uma heurística editorial, não uma previsão científica nem uma garantia de viralização ou renda.

## Executar no Windows

O projeto já contém `ffmpeg.exe`. Com o ambiente virtual existente:

```powershell
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements-ai.txt
python app.py
```

Para uma instalação nova:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-ai.txt
python app.py
```

Na primeira transcrição, o modelo Whisper selecionado (`tiny`, `base`, `small` ou `medium`) é baixado. `small` é o equilíbrio padrão; `tiny` é indicado para máquinas modestas. As fontes escolhidas precisam estar instaladas no Windows; caso contrário, o FFmpeg usa uma alternativa.

Por estabilidade, a transcrição usa CPU com `int8` por padrão. Em uma máquina com CUDA e bibliotecas NVIDIA compatíveis, a aceleração pode ser habilitada antes de abrir o app:

```powershell
$env:CLIPFORGE_WHISPER_DEVICE = "cuda"
$env:CLIPFORGE_WHISPER_COMPUTE_TYPE = "float16"
python app.py
```

## Arquitetura

```text
ui/                    interface e despacho thread-safe
downloaders/           adaptador universal do yt-dlp
core/                   modelos, enums e erros de domínio
services/
  transcription.py     faster-whisper local e lazy loading
  viral_analyzer.py     ranking explicável e fallback
  reaction_detector.py  amostragem de rostos com OpenCV
  captions.py           geração de ASS com karaokê
  ffmpeg.py             probe, cenas, progresso e cancelamento
  short_creator.py      orquestração e templates de render
tests/                  contratos do domínio e filtros
```

O motor não depende da GUI. Isso permite, como evolução, expô-lo por CLI/API, colocar jobs em fila e distribuir renderizações em workers sem reescrever as regras editoriais.

## Testes

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
python -m ruff check .
```

Além dos testes automatizados, a validação de integração deve renderizar um vídeo curto com o `ffmpeg.exe` distribuído antes de cada release.

## Caminho realista para produção e escala

1. Persistir jobs em SQLite/PostgreSQL e recuperar trabalhos interrompidos.
2. Criar uma CLI/API sobre `ShortCreationService` e workers com filas Redis/RQ ou Celery.
3. Adicionar codificação NVENC/AMF/Quick Sync selecionada por capacidade, com fallback x264.
4. Treinar rankers por nicho usando métricas consentidas de retenção — sem vender “viral garantido”.
5. Assinar builds, produzir instalador, sandbox de atualizações e testes em GPUs/CPUs diversas.
6. Integrar publicação apenas pelas APIs oficiais e com confirmação explícita do usuário.

## Privacidade e direitos

Use somente conteúdo próprio, licenciado, em domínio público ou autorizado. O app não remove DRM e não deve ser usado para contornar conteúdo privado ou termos de plataformas. Links podem exigir autenticação legítima; credenciais não são coletadas pela aplicação.
