# GravaTrem — Trem de Gravar os Trem (v0.0.1)

<img src="assets/logo-256.png" width="96" alt="Marca GravaTrem: monitor com ponto REC">

*O trem open-source que grava os trem da sua tela* para Windows: **tela inteira, janela ou região
livre** + **microfone e/ou áudio do sistema** → **MP4 (H.264 + AAC)**.
Interface moderna em Qt (PySide6), motor de captura sem dependências de UI.

![Requisitos](https://img.shields.io/badge/requer-Windows-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-green)
![Licença](https://img.shields.io/badge/licen%C3%A7a-MIT-lightgrey)

## Recursos

- 3 alvos: **Tela** (com seletor de monitor), **Janela** (lista + atualizar),
  **Região livre** (desenhar retângulo na tela, `ESC` cancela).
- 4 fontes de áudio: **Mic + sistema**, **Só mic**, **Só sistema**, **Sem áudio**
  (modos com sistema somem se não houver loopback WASAPI).
- Mixer ao vivo: VU segmentado com peak-hold + dB (mix, mic, sistema) e
  osciloscópio, funcionando parado e gravando.
- Preview ao vivo do alvo, foto PNG (F11), barrinha flutuante estilo Bandicam
  com timer durante a gravação.
- Painel: histórico de gravações (duração, tamanho, totais, disco livre).
- Atalhos: **F12** gravar/parar, **F11** foto.
- **Site**: GitHub Pages servindo a raiz (`Settings → Pages → Deploy from
  branch → /(root)`) — o site é o `index.html` da raiz (imagens em
  `docs/assets/`). Repo: `github.com/ryan-junio-oliveira/TremDeGravarOsTrem`.
- FPS 10/15/30, presets Performance (`ultrafast`) / Equilibrado (`veryfast`),
  cursor desenhado no vídeo (ligável), sempre-no-topo opcional.
- MP4 válido com PTS por relógio de parede (compensa GDI lento), áudio mono
  AAC 44.1 kHz, log rotativo com traceback em erros.

## Como funciona (resumo)

```
mss.grab ─► RGB ─► cursor ─► libx264 ─┐
                                      ├─► MP4 H.264 + AAC
mic + loopback ─► filas ─► mix mono ─► AAC ─┘
```

Detalhes técnicos (threads, timestamps, loopback, estado da UI):
[`docs/ARQUITETURA.md`](docs/ARQUITETURA.md). Histórico:
[`CHANGELOG.md`](CHANGELOG.md).

## Requisitos

- Windows 10/11 + Python 3.10+.
- Microfone opcional; áudio do sistema exige dispositivo WASAPI com loopback
  (a UI esconde os modos indisponíveis automaticamente).

## Instalação e execução

```bat
python -m pip install -r requirements.txt
python app.py
```

Ou dois cliques em **`Abrir-GravaTrem.bat`** (abre sem console).
Saída padrão: `%USERPROFILE%\Documents\GravaTrem\`
(`tela_AAAAMMDD_HHMMSS.mp4`, `foto_*.png`).

## Instalador (usuário final)

Baixe o `GravaTrem-Setup-X.Y.Z.exe` da release, execute e siga o assistente
(PT-BR/EN, instalação por usuário, sem admin). Como gerar o instalador a
partir do fonte: [`docs/BUILD.md`](docs/BUILD.md).

## Uso

1. Escolha o alvo (**Tela** + monitor, **Janela** da lista, **Região** desenhando
   o retângulo) e a fonte de áudio, FPS (10/15/30) e preset.
2. Ajuste o nível pelo mixer (VU + dB + osciloscópio ao vivo).
3. **REC** ou **F12** grava; a barrinha flutuante mostra timer; **Parar** salva
   e libera **▶ Reproduzir** / **Abrir pasta**.

## Configuração (`app.ini`)

| Chave | Valores | Padrão |
|---|---|---|
| `sOutputFolder` | caminho ou vazio (= `Documents\GravaTrem`) | vazio |
| `sLangFile` | `Portuguese(BR).ini`, `English.ini` | `Portuguese(BR).ini` |
| `dwFps` | `10`, `15`, `30` | `15` |
| `dwSampleRate` | taxa AAC | `44100` |
| `sAudioMode` | `both`, `mic`, `sys`, `none` | `both` |
| `sPresetLabel` | `Performance`, `Equilibrado` | `Equilibrado` |
| `sCapMode` | `full`, `win`, `reg` | `full` |
| `dwMonitor` | índice do monitor (mss, 1-based) | `1` |
| `sRegion` | `esquerda,topo,largura,altura` | vazio |
| `sShowCursor` | `1`, `0` | `1` |

Template comentado: `app.ini.example`. Idiomas em `lang/` (seção `[TEXT]`).

## Diagnóstico

- Log: `%APPDATA%\GravaTrem\logs\gravatrem.log` (1 MB, 3 cópias).
- Falhas de gravação/foto abrem diálogo e registram traceback no log.
- Sem áudio do sistema? Verifique se o dispositivo de saída tem loopback
  WASAPI e se `pyaudiowpatch` instalou corretamente.

## Estrutura

```
GravaTrem/
  app.py              UI Qt (MainWindow, FloatBar, RegionPicker, VU, scope)
  engine.py           Motor: captura, áudio, mux MP4, cursor, i18n, config
  app.ini / .example  Config ([GENERAL] VERSION + [OPTION] ...)
  lang/               Portuguese(BR).ini, English.ini
  docs/ARQUITETURA.md Arquitetura e pipeline detalhados
  docs/BUILD.md       Build e instalador (guia do dev)
  CHANGELOG.md        Histórico de versões
  `Abrir-GravaTrem.bat` Atalho sem console
  build.bat           Pipeline: deps → PyInstaller → instalador Inno Setup
  installer/          GravaTrem.iss (script do setup) + Output/ (instalador)
  icon.ico            Ícone (gerado por assets/make_logo.py)
  assets/             Marca: logo.svg, wordmark.svg, PNGs, make_logo.py
  docs/MARCA.md       Guia da marca (paleta, arquivos, regras)
  requirements.txt    mss, av, sounddevice, pyaudiowpatch, numpy, pillow,
                      PySide6, pywin32
```

## Limites / roadmap

- Só Windows; mix em mono; teto real ~23 fps a 30 configurados (GDI).
- Sem webcam overlay, NVENC, pausa/retomada ou MP3 — ver
  [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md) §6.

## Contribuindo

PRs são bem-vindos — ver [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Licença

MIT — ver [`LICENSE`](LICENSE).
