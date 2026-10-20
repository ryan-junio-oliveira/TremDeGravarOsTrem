# Design System — GravaTrem

Tema claro moderno, com o vermelho REC como única ação primária e verde
como cor de "ao vivo / ligado". Superfícies escuras só onde a natureza
pede: preview de vídeo, tooltip e overlay de região.
Fonte de verdade no código: `theme.py` (tokens + QSS). Este doc é a
especificação humana; em caso de divergência, vale o `theme.py`.

## 0. Princípios

1. **Uma ação primária por tela.** Só o REC é vermelho em gradiente
   (`#start`, `#recbtn`). Todo o resto é fantasma/neutro.
2. **Estado sempre textual, nunca só cor.** `● PRONTO` / `● GRAVANDO`,
   `● PREVIEW`, dB em texto + VU. Cor é redundância, não o canal.
3. **Densidade de cockpit.** Mixer, timer e FPS visíveis sem rolar;
   detalhes (pasta, preset, toggles) nos cards do rail direito.
4. **Tokens, nunca hex solto.** Todo hex vive uma vez em `theme.py`;
   `app.py` só referencia nomes. PR com hex literal fora de `theme.py`
   deve ser recusado (exceção: `rgba()` derivado de `RED` no RubberBand).

## 1. Cor (`theme.py`, bloco `1. cor`)

### Superfícies (claro → escuro)

| Token | Hex | Uso |
|---|---|---|
| `TXT`/`WHITE` | `#101828` / `#ffffff` | texto primário / ícones checked e texto sobre acentos |
| `MUTED` | `#5b6b82` | texto secundário, descrições |
| `DIM` | `#98a2b8` | captions caps e desabilitado (só texto grande) |
| `INK` | `#e9edf5` | texto sobre superfícies escuras (tooltip, overlay) |
| `BORDER_HI` | `#b9c4d6` | hover de borda |
| `BORDER` | `#dbe1ec` | borda padrão de tudo |
| `CARD2` | `#e0e6f0` | hover de controles, nav ativa |
| `CARD` | `#eef1f6` | botões e controles sobre o painel |
| `PANEL` | `#ffffff` | cards grandes, tabela |
| `SIDEBAR` | `#ffffff` | sidebar, topbar, FloatBar |
| `BG` | `#edf0f5` | fundo do app |
| `BG0` | `#10141d` | tooltip, overlay (superfície escura) |
| `PV_BG` | `#0d1117` | área do preview (sempre escura, como no OBS) |
| `INPUT` | `#eef1f6` | combos, scope, caixas de leitura |

### Acentos e status

| Token | Hex | Uso |
|---|---|---|
| `RED` | `#f04452` | REC, gravando, erro, mic clipado |
| `RED_HI` / `RED_GRAD_DK` | `#ff5a68` / `#d92d3b` | gradiente do REC (hover volta ao `RED` na base) |
| `RED_PRESSED` | `#b91c28` | REC pressionado |
| `RED_TINT` | `#fee2e2` | fundo do pill gravando e hover do stop |
| `GREEN` | `#16a34a` | live, toggle on, mic on, faixa baixa do VU |
| `GREEN_TINT` | `#dcfce7` | reservado |
| `CYAN` | `#0284c7` | "pronto", foco de combo, onda do mic |
| `AMBER` | `#b45309` | aviso, faixa média do VU/mix |
| `SELECT` | `#d9e7fd` | linha selecionada na tabela (texto `TXT`) |
| `VU_OFF` / `TRACK_OFF` | `#d8dfea` / `#cbd5e1` | segmento apagado / trilho off |

Apelidos legados (não usar em código novo): `BLUE` (= `GREEN`),
`MINT_DK` (= `GREEN_DK`), `RED_DK`.

### Mapeamento de status

| Estado | Pill | Texto |
|---|---|---|
| Pronto | `CARD` + `CYAN` | `● PRONTO` |
| Gravando | `RED_TINT` + `RED` | `● GRAVANDO` |
| Pausado | `AMBER_TINT` + `AMBER` | `❚❚ PAUSADO` |
| Salvo | `CARD` + `GREEN` | `● SALVO` (2 s) |
| Foto salva | mantém fundo + `TXT` | `● FOTO SALVA` (1,5 s) |
| Alvo indefinido | `CARD` + `RED` | `● DEFINA O ALVO` (1,5 s) |
| Clipagem (≥0,99) | texto `RED` | dB do canal |

## 2. Tipografia (`theme.py`, bloco `2. tipo`)

- UI: `Poppins` (empacotada em `assets/fonts/`, pesos 400/500/600/700,
  registrada via `QFontDatabase` no `main()`; fallback Segoe UI),
  pesos 500–600 no lugar do 700–800 (Poppins bold é largo).
- Mono (timer, dB, paths, hotkeys): `"Cascadia Code", "Consolas", monospace`
  (`FONT_MONO`).
- Escala: timer `#timer` 22pt/700 mono · título `#big` 14pt/600 −0.3px ·
  seção `#section` 10pt/600 · corpo 10pt · tabela 9.5pt · pill `#pill`
  9pt/600 · caption `#caps` 8pt/600 com tracking 1.2px e `DIM` ·
  hotkey `#hotkey` mono/700 com borda inferior dupla (efeito tecla).
- Números que mudam a cada tick (timer, dB) são sempre mono para não
  "pular" de largura.

## 3. Forma (`theme.py`, bloco `3. forma`)

- Raios: `R_SM` 8 (leitura/pills) · `R_MD` 10 (botões/combos) ·
  `R_LG` 12 (cards internos, tabela, start/stop) · `R_XL` 14 (cards) ·
  `R_PILL` 16 (FloatBar).
- Grade de 4px; passos 4/8/12/16/20/24. Margens de conteúdo 22/16,
  cards 16/14, gaps 10–12.
- Elevação: o QSS não tem sombra — profundidade se expressa com
  `BORDER` 1px + hover para `CARD2`/`BORDER_HI`. Não simular sombra com
  gradiente fora do REC.
- Motion: sem framework de animação; hover troca só cor/borda.
  VU tem peak-hold de 1 s e decaimento ×0,75 (`VUMeter`, `app.py:211`);
  é o único "movimento" do sistema.

## 4. Layout shell

- Janela mín. 1020×640 (padrão 1180×780). Coluna: sidebar 250px fixa
  (`_sidebar`, `app.py:513`) + coluna principal com topbar 68px
  (`_topbar`, `app.py:618`) e `QStackedWidget` de 4 páginas
  (Gravar, Gravações, Logs, Sobre).
- Topbar em duas zonas: seletor de alvo (só na Gravar) + divisor `vdiv`
  + cluster de ações globais (mic, foto, **REC/Pausar/Parar**) à direita.
  Mic/foto valem em qualquer aba (F12/F11 globais na janela); o seletor
  some nas demais (`_set_tab` alterna `segwrap`/`topdiv`) porque só a
  Gravar tem preview e ajustes. Durante a gravação o seletor trava
  (`setEnabled(False)`).
- Máquina de estados (`_rec_state`: idle/rec/paused, `_sync_rec_ui` como
  fonte única): REC desabilita gravando; Pausar vira Retomar; Parar e
  home-button acompanham; preview ganha borda `RED`/`AMBER`; título da
  janela mostra `●/❚❚ HH:MM:SS`; timer congela na pausa
  (`_rec_elapsed` desconta pausas); pill SALVO 2 s ao parar.
- Home (`_page_home`, `app.py:723`): esquerda flexível (título + preview
  16:9 mín. 420×236; alvo se escolhe no segmento da topbar) + rail direito
  308px com scroll (alvo → atalhos → vídeo → áudio → pasta → gravação, nessa
  ordem de frequência de ajuste).
- Regra anti-corte do rail: combos com conteúdo longo usam
  `AdjustToMinimumContentsLengthWithIcon` + `setMinimumContentsLength`
  (microfones e janelas têm nomes arbitrariamente longos); labels com
  `wordWrap` usam policy horizontal `Ignored` para quebrar linha em vez de
  estourar o viewport (scroll horizontal é sempre desligado); ações
  lado a lado só com textos curtos, senão empilha em largura total.
- Dashboard (`_page_dashboard`, `app.py:961`): 4 stat cards
  (ícone 20px + número 16pt/600 + caption) + tabela + linha de ações.
- Sobre (`_page_about`, `app.py:1078`): 1 card com marca + ações.
- Card base: `_card()` (`app.py:679`) — `#card`, 16/14, título `#caps`
  opcional; nunca colocar card dentro de card (usar `#cardflat` ou
  `INPUT` para leitura interna).

## 5. Componentes

### Botões

| ObjectName | Anatomia | Estados |
|---|---|---|
| `#start` | tinta escura (`TXT`), 12px radius, 13px pad, 11pt/600, dot `RED` | hover `INK_HOVER`; pressed `BG0` |
| `#stop` | `CARD2`, borda 1.5px `RED` | hover `RED_TINT` (mesmo tamanho do start — sem salto de layout) |
| `#recbtn` | como start, compacto 118×40 na topbar; texto `● REC`/`■ STOP` | idem start |
| `#recbtn` | REC tinta compacto (96×40, dot `RED` + texto branco) | hover `INK_HOVER`; disabled `CARD2`+`DIM` gravando (só F12/Retomar/Parar valem) |
| `#ghost` | `CARD`, borda, `MUTED`→`TXT` no hover | pressed `BORDER`; disabled `DIM` |
| `#ghost` Pausar/Parar | topbar 100–108×40, ícone + texto | Pausar↔Retomar troca texto/ícone; Parar ícone `RED`/`DIM`; disabled `DIM` |
| `#iconbtn` | 42×40 (44×40 mic), ícone FA 20px `TXT` | hover `CARD2`+`BORDER_HI`; checked = fundo `GREEN` com ícone `WHITE` (troca feita no código, ex. `_upd_dev_state`) |
| `#nav` | sidebar, texto à esquerda, ícone 20px | hover `CARD`; checked `CARD2`+borda (exclusivo via `QButtonGroup`) |
| `#seg` | dentro de `#segwrap` (`CARD`, 10px), ícone FA 13px + texto 9.5pt | checked = fundo `TXT`, texto/ícone `WHITE`; ícone troca no `_paint_seg` (`WHITE`/`MUTED`); disabled `DIM`; fonte única de escolha Tela/Janela/Região |

Regras: texto de ação com verbo (`Escolher…`, `Reproduzir`, `Iniciar
gravação`); reticência em ação que abre diálogo; atalho (F12/F11) sempre
visível próximo à ação, nunca só no tooltip.

### Inputs e toggles

- `QComboBox`: `INPUT`, borda `BORDER`, 10px radius, pad 10px (38px à
  direita para a seta); hover/focus viram `PANEL` (focus borda `CYAN` —
  único uso de ciano como borda); seta custom `assets/chevron-down.png`
  14px via `::down-arrow` (`theme.CHERVON`, com fallback silencioso);
  popup `PANEL` 10px radius + 6px pad, item 30px mín. com 6px radius,
  hover `CARD`, selecionado `SELECT`; disabled `DIM`.
- `Toggle` (`app.py:423`): trilho 40×22, off `TRACK_OFF`, on `GREEN`,
  knob branco 16px com sombra, label à direita; desabilitado = 55% opacidade.
  Hotkeys F12/F11 usam `Toggle` desabilitado + `#hotkey` (estado fixo,
  não controle).
- Leitura de path (`out_label`, `last_name`): `INPUT` + borda + 8px,
  texto `MUTED`/mono com `setToolTip` do path completo.
- `split_tracks` (`Toggle` no card de áudio): multitrilha OBS, habilitado
  só com Mic + sistema (`_upd_dev_state`), persistido em `sSplitTracks`.

### Indicadores

- `#pill`: 8px radius, 9pt/600; cores pelo §1.
- Live dot: `● PREVIEW` em `GREEN` / `● GRAVANDO` em `RED`, sempre com
  texto (nunca ponto sozinho).
- `VUMeter` (`app.py:211`): 10px, 28 segmentos, gap 3px; aceso
  `GREEN` <18 · `AMBER` <24 · `RED`; apagado `VU_OFF`; hold `TXT` 2px/1s.
- `WaveScope` (`app.py:252`): 64px, fundo `INPUT` 10px radius, linha
  central `BORDER`; mic `CYAN` para cima, sistema `GREEN` para baixo,
  traço 1.5px antialiased.
- `#badge` (resolução): `CARD`, 6px radius, `MUTED` mono.

### Tabela e listas

- `QTableWidget`: fundo `PANEL`, 12px radius, **sem grade** (`setShowGrid`
  off), zebra sutil (`AlternatingRowColors` → `CARD`), item 8–10px pad
  sem borda, hover `BORDER`, selecionado `SELECT` + `TXT`, `outline: 0`;
  cabeçalho `#caps`-like com underline `BORDER`; linhas 42px.
  Coluna Arquivo em Stretch, demais `ResizeToContents`; duplo-clique
  reproduz. Vazia: overlay `dash_empty` centralizado (filho do viewport
  + `eventFilter` de Resize, `WA_TransparentForMouseEvents`).

### Logs

- Página `Logs` (`_page_logs`): filtro (Tudo/INFO/Avisos/Erros, com
  ícones), `Toggle` Automático (refresh 2 s via `log_timer`, só com a
  aba aberta), `QPlainTextEdit` mono 9pt só-leitura sem wrap
  (`NoWrap`), rodapé com path + tamanho, botões Atualizar/Abrir pasta.
  Lê o tail de 400 linhas (`errors="replace"`); autoscroll ao final;
  estado vazio orienta a gravar algo.

### Overlays

- `FloatBar` (`app.py:334`): pill `SIDEBAR` 16px + `BORDER`, timer mono
  12pt/700, alvo em chip `CARD`, `● REC` 86×36. Arrastar pelo fundo;
  `X` para e esconde.
- `RegionPicker` (`app.py:282`): preto 45%, cursor crosshair,
  `QRubberBand` borda 2px `RED` + fill 12%, hint pill `BG0` no topo
  ("Arraste… • ESC cancela"); mín. 64×64.
- `QMessageBox` (primeira execução / erros): texto com path real e as
  duas saídas nomeadas (`Escolher pasta…` / `Usar padrão`).
- `QToolTip`: `BG0`, borda, 6px pad/radius. Tooltip complementa, nunca
  é o único rótulo.

### Scrollbar e separadores

- Vertical 10px transparente, alça `CARD2` 5px mín. 30px, hover
  `SCROLL_HI`; `#sep` 1px `BORDER`.

## 6. Ícones

Sistema único: **FontAwesome 5 sólido via `qtawesome`** (`fa5s.*`),
com fallback silencioso para texto quando a dependência falta
(`qta = None` → `fa_icon()` devolve `QIcon()` vazio, sem quebrar a UI).

Helpers em `app.py` (após o import do `theme`):
- `fa_icon(name, color=TXT)` → `QIcon` para botões e combos
  (`setIcon` + `setIconSize`).
- `fa_label(name, color=MUTED, size=16)` → `QLabel` só-ícone para
  compor linhas ícone + texto (dica, "livre em disco", stat cards).

Mapa vigente (nome → cor → tamanho):

| Onde | Ícone | Cor | px |
|---|---|---|---|
| nav Gravar/Gravações/Logs/Sobre | `video` / `film` / `file-alt` / `cog` | `TXT` | 20 |
| seg Tela/Janela/Região | `desktop` / `window-maximize` / `vector-square` | `MUTED` (`WHITE` c/ ativo) | 15 |
| FloatBar menu/foto/parar | `bars` / `camera` / `square` | `TXT` | 20 |
| toolbar mic/foto | `microphone` / `camera` | `TXT` (`WHITE` c/ mic on) | 20 |
| fonte de áudio (combo) | `headset` / `microphone` / `volume-up` / `volume-mute` | `MUTED` | 16 (nativo) |
| Iniciar/Parar | `circle` / `square` | `RED` / `WHITE` | 14 |
| Reproduzir / Atualizar / Definir região | `play` / `sync-alt` / `crop` | `MUTED` | 14–16 |
| pastas (Escolher/Abrir/logs) | `folder-open` | `MUTED` | 16 |
| dica / disco livre | `lightbulb` / `hdd` | `AMBER` / `MUTED` | 15–16 |
| stats Gravações/Espaço/Tempo/Livre | `film` / `hdd` / `clock` / `database` | `TXT` / `AMBER` / `CYAN` / `GREEN` | 20 |
| filtro de log | `list` / `info-circle` / `exclamation-triangle` / `exclamation-circle` | `MUTED` / `CYAN` / `AMBER` / `RED` | 16 (nativo) |
| sobre (código) | `code` | `MUTED` | 16 |
| atualizar lista (item do combo) | `sync-alt` via `setItemIcon` | `MUTED` | 16 (nativo) |

Regras:
- Set permitido: `fa5s` sólido. Nada de regular/brands sem motivo.
- Cor semântica: decorativo `MUTED`, ação `TXT`/`WHITE`, acento
  (`RED`/`AMBER`/`CYAN`/`GREEN`) só com significado (§1).
- **Zero emoji na UI.** Glifos geométricos `●`/`■`/`•` são linguagem
  do REC e ficam; todo o resto pictórico é FontAwesome.
- Set 100% FontAwesome: nav (`video`/`film`/`cog`), FloatBar
  (`bars`/`camera`/`times`), toolbar (`microphone`/`camera`) e todos os
  do mapa acima. O antigo `draw_icon()`/`dual_icon()` artesanal foi
  removido — não recriar ícones em QPainter.
- Novo ícone: validar o nome com `qta.icon()` em smoke antes de
  commitar (nomes FA5 em uso: `headset`, `microphone`, `volume-up`, `volume-mute`,
  `circle`, `square`, `play`, `sync-alt`, `crop`, `folder-open`, `film`,
  `hdd`, `clock`, `database`, `code`, `lightbulb`, `file-alt`,
  `list`, `info-circle`, `exclamation-triangle`, `exclamation-circle`…). Icones
  do `qtawesome` exigem `QApplication` existente antes da primeira
  chamada — na UI isso sempre vale (são criados nos builders).

## 7. Copy

PT-BR, verbo no infinitivo nos botões, substantivo nos cards em
`#caps` maiúsculo (`PASTA DE SAÍDA`, `FONTE DE ÁUDIO`). Unidades com
espaço (`15 FPS`, `44.1 kHz`); dB via `_db()` (`+xx dB` / `-inf dB`).
Tom mineiro só no site e no Sobre — a UI operacional é direta.

## 8. Acessibilidade

- Contrastes (sobre `PANEL` branco): `TXT` ~13:1; `MUTED` ~5:1 (texto
  normal ok); `DIM` só em caps grande/negrito ou desabilitado.
- Alvos de clique ≥36px (icon 40–44, REC 40, nav ~44).
- Nível de áudio duplo: barra + dB textual; clipagem pinta o dB de `RED`.
- Foco de teclado visível no combo (borda `CYAN`); diálogos com botões
  nomeados, sem "OK" genérico.

## 9. Evoluir o sistema

1. Novo token: acrescentar em `theme.py` §1 com comentário de uso +
   linha neste doc. Nunca reutilizar token "parecido".
2. Novo componente: criar `objectName` próprio no QSS (seção correta),
   fábrica/helper em `app.py` como `_card()`, e subseção no §5.
3. Checklist de PR visual: sem hex fora de `theme.py` · sem emoji na UI ·
   estados hover/pressed/disabled/checked cobertos · textos de estado (§1) ·
   smoke offscreen (`MainWindow` + troca de abas + dashboard) verde.
