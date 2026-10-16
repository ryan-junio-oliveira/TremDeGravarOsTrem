# Contribuindo com o GravaTrem

## Setup

```bat
python -m pip install -r requirements.txt
python app.py
```

## Regras

- `engine.py` **não pode** importar Qt/tkinter — é testável sem UI:
  `python -c "import engine"`.
- `app.py` concentra toda a UI; estado com fonte única (sem widgets espelho).
- Teste ponta a ponta antes do PR: grave ~3 s e confira o MP4
  (ex.: abrir com `av.open` e decodificar os frames de vídeo).
- Não commite `dist/`, `__pycache__/`, logs nem `app.ini` com caminhos da sua
  máquina (use defaults; documente chaves novas em `README.md` +
  `docs/ARQUITETURA.md` + `app.ini.example`).
- Idiomas: toda string nova da UI precisa entrar em
  `lang/Portuguese(BR).ini` e `lang/English.ini` (seção `[TEXT]`).
- Descreva mudanças no `CHANGELOG.md` sob `[Unreleased]`.
- Build/instalador: tudo documentado em [`docs/BUILD.md`](docs/BUILD.md)
  (1 comando: `build.bat`). Se mexer em imports condicionais, atualize os
  `--hidden-import` do `build.bat`; se mudar a versão, siga o checklist de
  release no `docs/BUILD.md` §5.
