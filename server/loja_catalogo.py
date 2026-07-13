"""
server/loja_catalogo.py
==========================
Catálogo de apps da "Loja Ultron" -- fonte de verdade do lado do
servidor (server/http_server.py serve isso em `GET /loja/catalogo`, e
os arquivos em `GET /loja/apps/<arquivo>`). Os mesmos `.apk` ficam
versionados em `site/apps/` (o site estático em HTML/CSS/TS, que
também lista esse catálogo, em `site/src/loja.ts`) -- os dois lados
duplicam os METADADOS de propósito (o site é 100% estático, nunca
chama o servidor), mas os ARQUIVOS `.apk` em si são os mesmos, servidos
direto de `site/apps/`, sem cópia duplicada em nenhum outro lugar.

Adicionar um app novo: coloque o `.apk` em `site/apps/`, adicione um
item aqui, E um item equivalente em `site/src/loja.ts` (recompile o
TypeScript -- ver site/README.md).
"""

import os

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPS_DIR = os.path.join(_BASE_DIR, "site", "apps")

CATALOGO = [
    {
        "id": "ultron-companion",
        "nome": "Ultron Companion",
        "categoria": "Produtividade",
        "resumo": "O Ultron no seu bolso -- controla o celular e conversa com o núcleo do PC pela Wi-Fi.",
        "versaoNome": "1.5",
        "versaoCodigo": 6,
        "arquivo": "ultron-companion.apk",
    },
    {
        "id": "ultron-loja",
        "nome": "Loja Ultron",
        "categoria": "Sistema",
        "resumo": "A própria loja -- descobre o Ultron na rede e instala/atualiza os apps do ecossistema.",
        "versaoNome": "1.0",
        "versaoCodigo": 1,
        "arquivo": "ultron-loja.apk",
    },
    {
        "id": "redcore-mobile",
        "nome": "RedCore",
        "categoria": "Navegador",
        "resumo": "O navegador do Ultron, agora no celular -- abas, busca embutida, mesmo visual do PC.",
        "versaoNome": "1.0",
        "versaoCodigo": 1,
        "arquivo": "redcore-mobile.apk",
    },
]


def listar() -> list:
    """Catálogo + tamanho real em MB, calculado do arquivo no disco
    (nunca um número fixo no código -- sempre bate com o que está de
    fato em site/apps/). `disponivel=False` quando o .apk ainda não
    foi compilado/colocado lá -- o cliente decide se esconde ou marca
    como "em breve"."""
    resultado = []
    for app in CATALOGO:
        caminho = os.path.join(APPS_DIR, app["arquivo"])
        existe = os.path.isfile(caminho)
        tamanho_mb = round(os.path.getsize(caminho) / (1024 * 1024), 1) if existe else None
        resultado.append({**app, "tamanhoMb": tamanho_mb, "disponivel": existe})
    return resultado


def caminho_apk(arquivo: str) -> str:
    """Resolve o caminho de um .apk do catálogo com segurança -- só
    aceita o nome de arquivo EXATO de uma entrada já cadastrada (nunca
    um caminho arbitrário vindo da URL), evitando path traversal (ex.:
    '../../config/config.json'). Retorna "" se não for um nome
    conhecido ou o arquivo não existir."""
    nomes_validos = {app["arquivo"] for app in CATALOGO}
    if arquivo not in nomes_validos:
        return ""
    caminho = os.path.join(APPS_DIR, arquivo)
    return caminho if os.path.isfile(caminho) else ""
