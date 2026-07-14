"""
automacao/redcore_favoritos.py
==================================
Favoritos do RedCore (gui/redcore.py) -- mesma tabela/banco de
`redcore_historico.py` (data/jarvis.db), só que guardando páginas que o
usuário marcou de propósito (⭐ na barra de ferramentas) em vez de todo
mundo que passou pela navegação.
"""

from datetime import datetime

from core.database import get_database

_SCHEMA = """
CREATE TABLE IF NOT EXISTS redcore_favoritos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    url TEXT NOT NULL,
    titulo TEXT,
    criado_em TEXT NOT NULL,
    UNIQUE(user_id, url)
);
"""


def _ensure_schema():
    get_database().executescript(_SCHEMA)


def adicionar(user_id: str, url: str, titulo: str = "") -> bool:
    """Adiciona (ou atualiza o título de) um favorito. Retorna True se
    era novo, False se já existia (só atualizou o título) ou se a url
    não é http(s) (rejeitado, sem gravar nada).

    Só http(s) -- gui/redcore.py:_gerar_html_nova_aba e o
    gerarHtmlNovaAba() do RedCore Mobile renderizam favoritos como
    `<a href="...">` clicável; sem essa validação, uma url tipo
    `javascript:...` salva via POST /redcore/favoritos (server/
    http_server.py:_alterar_favorito_redcore) executaria script na
    origem do navegador assim que a nova aba (speed dial) fosse aberta."""
    if not url.startswith("http://") and not url.startswith("https://"):
        return False
    _ensure_schema()
    ja_existia = get_database().query_one(
        "SELECT id FROM redcore_favoritos WHERE user_id=? AND url=?", (user_id, url)
    )
    if ja_existia:
        get_database().execute(
            "UPDATE redcore_favoritos SET titulo=? WHERE user_id=? AND url=?",
            (titulo or "", user_id, url),
        )
        return False
    get_database().execute(
        "INSERT INTO redcore_favoritos (user_id, url, titulo, criado_em) VALUES (?,?,?,?)",
        (user_id, url, titulo or "", datetime.now().isoformat()),
    )
    return True


def remover(user_id: str, url: str) -> bool:
    _ensure_schema()
    linha = get_database().query_one(
        "SELECT id FROM redcore_favoritos WHERE user_id=? AND url=?", (user_id, url)
    )
    if not linha:
        return False
    get_database().execute("DELETE FROM redcore_favoritos WHERE user_id=? AND url=?", (user_id, url))
    return True


def esta_favoritado(user_id: str, url: str) -> bool:
    _ensure_schema()
    linha = get_database().query_one(
        "SELECT id FROM redcore_favoritos WHERE user_id=? AND url=?", (user_id, url)
    )
    return linha is not None


def listar(user_id: str) -> list:
    _ensure_schema()
    return get_database().query(
        "SELECT * FROM redcore_favoritos WHERE user_id=? ORDER BY id DESC", (user_id,)
    )
