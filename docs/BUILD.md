# Build e instalador — guia do dev

Como sair do código-fonte até o `GravaTrem-Setup-X.Y.Z.exe` pronto para
distribuir. Para regras de contribuição (estilo, i18n, changelog), ver
[`CONTRIBUTING.md`](../CONTRIBUTING.md).

## 1. Pré-requisitos

- Windows 10/11 64-bit + Python 3.10+ no `PATH`.
- [Inno Setup 6](https://jrsoftware.org/isinfo.php) (o `build.bat` procura
  `iscc` no `PATH` ou em `C:\Program Files (x86)\Inno Setup 6\ISCC.exe`).
- Todo o resto (`requirements.txt` + PyInstaller) o `build.bat` instala.

## 2. Pipeline (1 comando)

```bat
build.bat
```

| Etapa | O que faz | Falha se... |
|---|---|---|
| 1. Python | `python --version` | Python fora do `PATH` |
| 2. Deps | `pip install -r requirements.txt` + PyInstaller | rede/pip quebrado |
| 3. Bundle | PyInstaller `--onedir --windowed` → `dist\GravaTrem\` | erro de import/hook |
| 4. Valida | confere `GravaTrem.exe` + `_internal\lang\*.ini` | bundle incompleto |
| 5. Setup | `ISCC /DAppVersion=... installer\GravaTrem.iss` | Inno ausente, `dist\` fora do esperado |

Artefato final: `installer\Output\GravaTrem-Setup-<VERSAO>.exe` (~250–500 MB:
Qt + FFmpeg + PortAudio embutidos — normal).

## 3. Por que esses flags do PyInstaller

```
--onedir      abre mais rápido e o antivirus reclama menos que --onefile
--windowed    sem janela de console (o app já loga em arquivo)
--icon        icon.ico no exe
--add-data "lang;lang"   i18n lida em runtime via BASE_DIR (engine.load_lang);
                         sem isso o app cai para English e o prefixo vira "screen"
--hidden-import win32gui  importado dentro de função (get_cursor_pos,
                         _list_windows); o PyInstaller não o detecta sozinho
--add-data "icon.ico;."   a titlebar e o ícone da janela carregam icon.ico em
                         runtime; sem isso o bundle fica sem logo e a taskbar
                         usa só o ícone embutido no exe
```

`sounddevice`, `av`, `numpy`, `PIL`, `pyaudiowpatch` são detectados
automaticamente (hooks + imports de topo em `engine.py`). Se adicionar um
import condicional novo, registre o `--hidden-import` correspondente no
`build.bat` e teste o bundle.

## 4. O script Inno (`installer/GravaTrem.iss`)

- Instala em `{autopf}\GravaTrem` **por usuário** (`PrivilegesRequired=lowest`,
  sem UAC) com página de grupo desabilitada e estilo moderno.
- Empacota `dist\GravaTrem\*` recursivo (exe + `_internal` + `lang`).
- Idiomas do assistente: PT-BR + EN. Atalhos: Menu Iniciar sempre,
  Desktop opcional. Opção de executar ao concluir.
- **Não instala `app.ini` de propósito**: o motor tolera config ausente
  (usa defaults e grava ao final da primeira gravação). Cada usuário gera
  a sua — sem conflito de permissão nem config alheia vazando.
- `AppId` é um GUID fixo: **não mude** (o Windows usa para upgrades e
  desinstalação limpa). Versão vem da linha de comando (`/DAppVersion=`).

## 5. Lançar nova versão (checklist)

1. `app.py`: `APP_VERSION = "X.Y.Z"`.
2. `app.ini` + `app.ini.example`: `[GENERAL] version = X.Y.Z`.
3. `build.bat`: `set VERSION=X.Y.Z`.
4. `CHANGELOG.md`: mover `[Unreleased]` → `[X.Y.Z]` com data.
5. Rodar `build.bat`, testar o setup (seção 6) e anexar o exe à release.

## 6. Testando o instalador

```bat
REM instalacao silenciosa por usuario + abre o app instalado (smoke)
installer\Output\GravaTrem-Setup-0.0.1.exe /SILENT
"%LOCALAPPDATA%\Programs\GravaTrem\GravaTrem.exe"
REM desinstalacao silenciosa
"%LOCALAPPDATA%\Programs\GravaTrem\unins000.exe" /SILENT
```

O que conferir: atalhos criados, primeira gravação de ~3 s gera MP4 válido,
`%APPDATA%\GravaTrem\logs\trem.log` sem traceback, desinstalação não deixa
a pasta nem a entrada em "Aplicativos instalados".

## 7. Problemas comuns

| Sintoma | Causa provável | Ação |
|---|---|---|
| `ERRO: lang nao embutido` | `--add-data` com separador errado | no Windows o separador é `;` (no Linux, `:`) |
| Prefixo dos MP4 vira `screen` | `lang/` fora do bundle | refazer etapa 3, conferir `_internal\lang\` |
| `win32gui` ImportError no exe | faltou hidden-import | conferir flag no `build.bat` |
| `ISCC.exe nao encontrado` | Inno não instalado / fora do PATH | instalar Inno 6 ou `set PATH` |
| Antivírus segura o setup | exe unsigned + PyInstaller | assinar com certificado (futuro) ou liberar pasta |
| Setup pede admin | `PrivilegesRequired` alterado | manter `lowest` |

## 8. Estrutura dos artefatos

```
dist\GravaTrem\GravaTrem.exe   bundle (NAO versionar; ver .gitignore)
dist\GravaTrem\_internal\      Qt, FFmpeg, PortAudio, lang, app compilado
installer\Output\GravaTrem-Setup-X.Y.Z.exe   instalador final (NAO versionar)
```
