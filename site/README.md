# site/ — dossiê e loja do Ultron

Site estático (HTML + CSS + TypeScript puro, sem framework) com duas
páginas:

- **`index.html`** — dossiê explicando como o assistente pessoal
  Ultron funciona por dentro. Conteúdo explicativo, não é um painel de
  controle (não fala com o servidor local nem expõe nenhum dado de
  verdade).
- **`loja.html`** — loja pra baixar os apps do ecossistema (hoje só o
  Ultron Companion, `apps/ultron-companion.apk`) direto deste
  repositório, sem loja de terceiros.

Só abrir os arquivos `.html` no navegador já funciona -- `dist/*.js`
(a saída compilada do TypeScript) já vem pronta no repositório, não
precisa rodar nada antes.

## Editar

O código fonte de verdade fica em `src/*.ts`. Depois de editar, recompile:

```powershell
cd site
npm install    # só na primeira vez
npm run build  # gera dist/*.js a partir de src/*.ts
```

`npm run watch` recompila sozinho a cada alteração salva.

## Adicionar um app novo na loja

Copie o `.apk` pra `apps/`, e adicione um item no array `CATALOGO` em
`src/loja.ts` (nome, versão, tamanho, descrição, caminho do arquivo).
A página se desenha sozinha a partir dessa lista -- não precisa mexer
no HTML.

## Estrutura

```
site/
├── index.html          # dossiê -- estrutura/conteúdo
├── loja.html             # loja -- estrutura/conteúdo
├── style.css               # visual compartilhado (tema claro/escuro via [data-theme])
├── loja.css                 # visual específico da loja (cards de app)
├── apps/                      # .apk publicados, servidos como arquivo estático
│   └── ultron-companion.apk
├── src/
│   ├── theme.ts                # alternância de tema (compartilhado pelas duas páginas)
│   ├── main.ts                  # efeito de "boot" do dossiê
│   └── loja.ts                   # catálogo de apps + renderização dos cards
├── dist/                          # TypeScript compilado (o que o navegador carrega)
└── tsconfig.json                   # strict mode, sem módulos (script clássico -- funciona via file://)
```
