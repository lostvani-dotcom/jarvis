# site/ — dossiê e loja do Ultron

Site estático (HTML + CSS + TypeScript puro, sem framework) com duas
páginas:

- **`index.html`** — dossiê explicando como o assistente pessoal
  Ultron funciona por dentro. Conteúdo explicativo, não é um painel de
  controle (não fala com o servidor local nem expõe nenhum dado de
  verdade).
- **`loja.html`** — loja pra baixar os apps do ecossistema (Ultron
  Companion, Loja Ultron e RedCore Mobile, em `apps/`) direto deste
  repositório, sem loja de terceiros.

Só abrir os arquivos `.html` no navegador já funciona -- `dist/*.js`
(a saída compilada do TypeScript) já vem pronta no repositório, não
precisa rodar nada antes.

## Acessar pela rede (sem abrir o arquivo local)

Com o Ultron rodando no PC, `server/http_server.py` também serve este
site inteiro -- alcançável do celular ou de qualquer aparelho na mesma
Wi-Fi, não só abrindo o arquivo no PC:

- `http://<ip-do-pc>:8765/loja` -> loja.html
- `http://<ip-do-pc>:8765/dossie` -> index.html
- `http://<ip-do-pc>:8765/site/<qualquer arquivo>` -> serve qualquer
  arquivo daqui direto (CSS/JS/APKs inclusos)

## Editar

O código fonte de verdade fica em `src/*.ts`. Depois de editar, recompile:

```powershell
cd site
npm install    # só na primeira vez
npm run build  # gera dist/*.js a partir de src/*.ts
```

`npm run watch` recompila sozinho a cada alteração salva.

## Adicionar um app novo na loja

Copie o `.apk` pra `apps/`, adicione um item no array `CATALOGO` em
`src/loja.ts` (nome, versão, tamanho, descrição, caminho do arquivo),
E um item equivalente em `server/loja_catalogo.py` (pra ficar
disponível também no app "Loja Ultron" do celular, que busca o
catálogo do servidor em vez de ter uma lista fixa). A página/app se
desenham sozinhos a partir dessas listas -- não precisa mexer no HTML
nem recompilar nenhum APK.

## Estrutura

```
site/
├── index.html          # dossiê -- estrutura/conteúdo
├── loja.html             # loja -- estrutura/conteúdo
├── style.css               # visual compartilhado -- só escuro, de propósito (ver style.css)
├── loja.css                 # visual específico da loja (cards de app, cor por categoria)
├── apps/                      # .apk publicados, servidos como arquivo estático
│   ├── ultron-companion.apk
│   ├── ultron-loja.apk
│   └── redcore-mobile.apk
├── src/
│   ├── main.ts                  # efeito de "boot" do dossiê (personalizado com o nome do operador)
│   └── loja.ts                   # catálogo de apps + renderização dos cards
├── dist/                          # TypeScript compilado (o que o navegador carrega)
└── tsconfig.json                   # strict mode, sem módulos (script clássico -- funciona via file://)
```
