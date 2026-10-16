# Changelog

## [Unreleased]

### Renomeado
- Projeto agora se chama **Trem de Gravar os Trem** (curto: **GravaTrem**,
  "o trem que grava os trem da sua tela"): título da janela, `Abrir-GravaTrem.bat`,
  pastas de saída (`Documents\GravaTrem`) e logs
  (`%APPDATA%\GravaTrem\logs\gravatrem.log`), README, docs e LICENSE.

### Removido
- `app_tk_legado.py` (interface tkinter descontinuada; ~570 linhas, incluindo
  `App`, `VUMeter`/`WaveScope` em tkinter). O motor de captura foi preservado
  integralmente em `engine.py`, sem nenhuma dependencia de tkinter.
- Páginas ocultas de Vídeo/Áudio (`_hidden_page`, `_page_video`, `_page_audio`
  e os combos espelhados `*_mini`/`*_tab` com sincronização cruzada).
  Todos os controles agora têm fonte única na tela inicial.
- `dist/` (artefato de build, ~472 MB) e `__pycache__/` do repositório.
- `VERSAO-v0.0.1.md` (conteúdo migrado para este changelog).
- Import não utilizado (`traceback`) em `app.py`.

### Corrigido
- `requirements.txt` agora declara `pywin32` (usado em `get_cursor_pos` e na
  listagem de janelas, mas faltava na lista).
- `app.ini` sanitizado para defaults (antes continha monitor/região/pasta da
  máquina do desenvolvedor). Adicionado `app.ini.example` comentado.
- Toggle do microfone na toolbar não disparava mais `abtns` inexistentes;
  estado agora é fonte única (`self.amode`).
- Níveis mic/sistema + osciloscópio agora visíveis na barra lateral (antes
  existiam só em página oculta); timer, FPS real e espaço livre também
  voltaram para a tela inicial.

### Adicionado
- Marca própria: `assets/` (logo.svg, wordmark.svg, PNGs, gerador
  `make_logo.py`) + `icon.ico` novo no app/exe/instalador. Guia em
  `docs/MARCA.md`.
- Aba **Painel**: cards (gravações, espaço usado, tempo gravado, disco livre)
  + histórico com data/duração/tamanho, reproduzir e atualizar.
- Site estático para GitHub Pages em `docs/index.html` (+ `docs/assets/`).
- `engine.py`: módulo do motor (captura, áudio, mux) sem dependências de UI.
- `build.bat`: pipeline de 1 comando (deps → PyInstaller → Inno Setup).
- `installer/GravaTrem.iss`: setup por usuário (sem admin), PT-BR/EN,
  sem `app.ini` embutido (cada usuário gera o seu). Detalhes em
  `docs/BUILD.md`.
- `app.ini.example`, `.gitignore`, `LICENSE` (MIT), `docs/ARQUITETURA.md`,
  `README.md` reescrito, `Abrir-GravaTrem.bat` atualizado.

## [0.0.1] — primeira versão empacotada

### Executar (sem instalar Python)
- Build standalone em `dist/` (não versionado): Qt + FFmpeg + PortAudio
  embutidos (~244 MB).

### Executar do código-fonte
```bat
python -m pip install -r requirements.txt
python app.py
```
ou dois cliques em `Abrir-GravaTrem.bat`.

### Diagnóstico
- Log: `%APPDATA%\GravaTrem\logs\gravatrem.log` (gira a cada 1 MB, 3 cópias).
- Erros de gravação/foto abrem diálogo e registram traceback no log.
- Config: `app.ini` (`sAudioMode`, `sCapMode`, `dwMonitor`, `sRegion`,
  `sShowCursor`, `dwFps`, `sPresetLabel`).
- Saída padrão: `%USERPROFILE%\Documents\GravaTrem\`.

### Verificado nesta versão
- Gravação MP4 `h264+aac` de ponta a ponta (744 frames decodificados).
- Correção: cursor na borda da tela não quebra mais a gravação.
- Fluidez medida: 15.0 fps reais a 15 configurados; ~23 a 30 (teto do GDI).
- Tela 1600x900 H264 OK; mic+loopback mixados em mono AAC OK
  (4 s: 40 pkts vídeo, 168 pkts áudio, 3.85 s).
- Cursor: 9.7 ms → 0.03 ms/frame (sprite numpy).
