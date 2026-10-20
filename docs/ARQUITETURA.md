# Arquitetura — GravaTrem

Documento técnico de como o sistema funciona. Visão de usuário está no
`README.md`.

## 1. Mapa dos módulos

```
app.py        UI Qt (PySide6): MainWindow, FloatBar, RegionPicker,
              VUMeter, WaveScope, Toggle, fa_icon/fa_label (FontAwesome)
theme.py      Design system claro: tokens + QSS (fonte única, ver DESIGN_SYSTEM.md)
engine.py     Motor sem UI: captura (mss), áudio (sounddevice +
              pyaudiowpatch), mux (PyAV), cursor, i18n, config
app.ini       Config persistida ([GENERAL] + [OPTION])
lang/*.ini    i18n (Portuguese(BR), English) — seção [TEXT]
icon.ico      Ícone da janela
Abrir-GravaTrem.bat  Atalho Windows (pythonw, sem console)
```

`app.py` importa do motor apenas:

```python
from engine import (APP_INI, HAS_LOOPBACK, LiveMonitor,
                    default_output_folder, load_lang,
                    new_meter, record_screen)
```

Não há import reverso: o motor nunca importa a UI. Testes do motor rodam
sem Qt (ex.: `python -c "import engine"`).

## 2. Pipeline de gravação (`engine.record_screen`)

```
mss.grab(região) ──► BGRA→RGB ──► draw_cursor ──► libx264 ──┐
                                                            ├─► MP4 (av.open)
mic (sounddevice cb) ──► mic_q ──┐                           │
                                 ├─► mix mono ──► AAC ───────┘
loopback (pyaudiowpatch) ─► sys_q ┘  (janelas de 1024 amostras)
```

1. **Vídeo**: loop no período `1/fps`; `sct.grab(mon)`; conversão
   `BGRA→RGB` via numpy; cursor desenhado por cima (`draw_cursor` com
   sprite RGBA pré-renderizado — 0.03 ms/frame); `VideoFrame` com
   `pts` ancorado no **relógio de parede** (`(now - t_start) * fps`),
   com clamp monotônico (`frame.pts >= vpts`), o que compensa frames
   lentos do GDI sem dessincronizar. Codec `libx264`, `yuv420p`,
   `tune=zerolatency`, preset `ultrafast` (Performance) ou `veryfast`
   (Equilibrado). Largura/altura forçadas a múltiplo de 2 (exigência
   do yuv420p).
2. **Áudio**: callbacks `mic_cb`/`sys_cb` enfileiram chunks com timestamp
   em `mic_q`/`sys_q`. O loop drena as filas, tolera um lado travado
   (após 0.5 s sem dados segue só com o lado vivo) e soma os dois lados
   em **mono** (`mic_buf + sys_buf`, truncando no menor). O buffer
   `pend` acumula o resto `< 1024` entre iterações; cada janela de 1024
   vira um `AudioFrame` (`fltp`, mono) com `pts` ancorado no relógio de
   parede na primeira janela (`apts`). Stream AAC só existe se houver
   pelo menos uma fonte — modo `none` gera MP4 só-vídeo.
3. **Parada**: `stop_event: threading.Event` (setado por `on_stop`);
   ao sair do loop, drena os encoders (`encode(None)`) e fecha o
   container — o MP4 só é válido após esse flush.

Região gravada (`MainWindow._current_region`):
- `full`: monitor N via `mss.monitors[dwMonitor]`.
- `win`: `win32gui.GetWindowRect(hwnd)` da janela escolhida (mín. 64x64).
- `reg`: retângulo do `RegionPicker` persistido em `sRegion`.

## 3. Monitoração ao vivo (`LiveMonitor` + `meter`)

Fora da gravação, `LiveMonitor.start(mic_id, sys_on)` mantém os mesmos
streams abertos em modo callback só para alimentar o `meter`:

```python
meter = {"mic": (pico, ts), "sys": (pico, ts),
         "wave_mic": deque(240), "wave_sys": deque(240)}
```

- `VUMeter.set(nível)`: 28 segmentos (18 verdes, 6 âmbar, 4 vermelhos)
  + peak-hold branco de 1 s.
- `WaveScope`: mic acima da linha média (ciano), sistema abaixo (verde).
- `MainWindow._poll` (QTimer 120 ms): aplica decaimento (`*0.75` após
  0.25 s sem pico), atualiza dB (`20*log10(pico)`), mix, scope, timer e
  `FPS real` (frames/segundo via `status_cb` → `_frame_tick`).
- Ao gravar, o monitor de idle é parado e o `meter` é recriado zerado;
  os callbacks de gravação alimentam o mesmo dict, então VU/scope
  continuam vivos durante a gravação. Ao parar, o monitor reinicia.

Loopback: `_find_loopback()` casa o dispositivo WASAPI de saída padrão
com seu par `isLoopbackDevice` pelo nome; sem `pyaudiowpatch` ou sem par,
`HAS_LOOPBACK=False` e os modos `both`/`sys` somem da UI.

## 4. UI Qt (`app.py`)

- `MainWindow`: sidebar (logo + `v0.0.1`, nav Gravar/Gravações/Logs/Sobre,
  card de status com timer + FPS, dica, abrir pasta) + topbar (segmento
  Tela/Janela/Região, toggle mic, foto, REC/Pausar/Parar) + `QStackedWidget`
  de 4 páginas. Estados via `_sync_rec_ui` (idle/rec/paused); F12 =
  gravar/parar/retomar; fechar durante gravação pede confirmação.
- Tela inicial (`_page_home`): preview (`QLabel` + badge de resolução),
  hotkeys fixas (F12 REC, F11 foto — `QShortcut`), alvo, `always-on-top`,
  cursor, fonte de áudio, VU mix + VU mic/sys + scope, FPS/preset,
  disco livre, pasta de saída, última gravação (reproduzir/pasta).
- Gravações (`_page_dashboard`): stat cards + tabela sem grade com zebra,
  hover, colunas inteligentes, empty state e duplo-clique que reproduz.
- Logs (`_page_logs`): filtro por nível, auto-refresh 2 s (`log_timer`,
  só com a aba aberta), viewer mono só-leitura com tail de 400 linhas,
  path + tamanho no rodapé.
- Preview: `_preview_tick` (50 ms) dispara thread que faz `grab` +
  `QImage` e emite `preview_ready(QImage, vw, vh)`; guardas `_pv_busy`
  + `_pv_last_emit` (1.5 s) evitam acúmulo se o DWM engasgar. Durante a
  gravação o preview pausa (retorna cedo se `stop_event` ativo).
- `FloatBar`: barrinha `FramelessWindowHint|StaysOnTop|Tool` com
  menu/resolução/alvo/timer/REC/foto/fechar; arrastável; fixada no topo
  da tela (rente à borda superior); `tick(s)` formata `HH:MM:SS`.
- `RegionPicker`: `QDialog` fullscreen translúcido cobrindo a união de
  todos os monitores (`QGuiApplication.screens()`), `QRubberBand`,
  mínimo 64x64, ESC cancela, coordenadas convertidas para o espaço
  virtual (`geometry().x/y + rect`).
- Estado: `self.amode` (`both|mic|sys|none`), `self.capmode`
  (`full|win|reg`), combos únicos (`amode_box`, `dev_box`, `fps_box`,
  `preset_box`) — sem espelhos. `on_record` persiste tudo no `app.ini`.
- Multitrilha estilo OBS (`sSplitTracks`, toggle no card de áudio, só com
  `both`): `record_screen(..., split_tracks=True)` grava 3 faixas AAC
  (mix + mic + sistema isolados, com `title` Mix/Microfone/Sistema).
  Faixas isoladas consomem só as amostras novas da iteração (sobras do
  mix não duplicam); cada faixa tem `pend` + âncora de PTS próprios.
  Com uma fonte só, cai para faixa única sozinho.
- Pausa (`pause_event`): worker congela relógio/preview e descarta áudio
  acumulado; ao retomar, `t_start` desloca (pausa cortada, sem buraco)
  e `nxt` reinicia (sem rajada). Preview ao vivo sai do worker via
  `preview_cb(rgb, w, h)` throttled (`preview_interval`, padrão 0.2 s).
- Erros de gravação/foto: `error_sig` (thread-safe) → `QMessageBox` +
  traceback no log rotativo (`%APPDATA%\GravaTrem\logs\gravatrem.log`,
  1 MB x 3).

## 5. Config (`app.ini`) e i18n (`lang/`)

| Chave | Seção | Valores | Efeito |
|---|---|---|---|
| `version`, `beta` | GENERAL | — | exibição |
| `sOutputFolder` | OPTION | caminho ou vazio | vazio = `Documents\TremDeGravarOsTrem` |
| `sLangFile` | OPTION | `Portuguese(BR).ini` / `English.ini` | prefixo do MP4 (`tela`/`screen`), rótulos |
| `dwFps` | OPTION | `10`/`15`/`30` | taxa alvo (real limitada pelo GDI, ~23) |
| `dwSampleRate` | OPTION | `44100` | taxa do AAC/monitor |
| `sAudioMode` | OPTION | `both`/`mic`/`sys`/`none` | fontes de áudio |
| `sPresetLabel` | OPTION | `Performance`/`Equilibrado` | `ultrafast`/`veryfast` |
| `sCapMode` | OPTION | `full`/`win`/`reg` | alvo |
| `dwMonitor` | OPTION | índice mss (1-based) | monitor em `full` |
| `sRegion` | OPTION | `l,t,w,h` | região em `reg` |
| `sShowCursor` | OPTION | `1`/`0` | desenhar cursor |
| `sSplitTracks` | OPTION | `1`/`0` | multitrilha (mix+mic+sys); só com `both` |

## 6. Limites conhecidos e próximos passos

- Só Windows (`win32gui`, `os.startfile`, WASAPI loopback).
- Sem seleção de codec/container (sempre MP4 H.264 + AAC mono).
- FPS real teto ~23 a 30 fps (GDI); sem NVENC/GPU.
- Sem webcam overlay, sem pausa/retomada, sem MP3.
- Janela (`win`) captura coordenadas estáticas (não segue a janela).
