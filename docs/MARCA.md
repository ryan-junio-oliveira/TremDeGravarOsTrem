# Marca — GravaTrem

## Conceito

Tile escuro arredondado (o app) + monitor com ponto **REC** vermelho (o que o
trem faz). O vermelho é sempre o acento de "gravando"; o resto da marca vive
nos tons da interface — a marca e o app são o mesmo sistema visual.

## Arquivos (`assets/`)

| Arquivo | Uso |
|---|---|
| `logo.svg` | Vetor do símbolo (fonte da verdade; edite este) |
| `wordmark.svg` | Símbolo + "GravaTrem" + tagline (cabeçalhos, release) |
| `logo-512/256/128/64/32.png` | README, docs, web — gerados, não edite à mão |
| `make_logo.py` | Gerador: `python assets/make_logo.py` (saída em `assets/` + `icon.ico`) |
| `icon.ico` (raiz) | Ícone da janela, do exe e do instalador — gerado, multi-resolução |

Regra: mudou a marca, rode `make_logo.py` e commite o `.svg` + PNGs + ICO
juntos. O próximo `build.bat` já leva o ICO novo para o exe e o setup.

## Paleta

| Nome | Hex | Onde |
|---|---|---|
| Fundo claro | `#262D40` | topo do tile |
| Fundo escuro | `#141821` | base do tile |
| REC | `#E5484D` | ponto, "Trem" no wordmark |
| Texto | `#E8EAF0` | moldura do monitor, "Grava" |
| Mudo | `#9AA3B5` | pé do monitor, tagline |

## Regras

- Não mude o vermelho do ponto (é o "gravando" universal do app).
- Não estique, não gire, não aplique sombra externa — o tile já tem volume.
- Tamanho mínimo digital: 32 px (abaixo disso, use só o ponto REC).
- Fundo: use sobre superfícies escuras; sobre fundo claro, prefira o
  `wordmark.svg` (que leva tile próprio).
