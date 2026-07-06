"""
automacao/redcore_historico.py
==================================
Histórico de navegação do RedCore (gui/redcore.py, o navegador do
Ultron) -- toda URL/título visitado é registrado aqui, pra o Ultron
"ver tudo que você usa" (pedido explícito do usuário) e responder
coisas como "o que eu vi hoje" / "o que eu pesquisei sobre X".

Honesto sobre o escopo: isso é SÓ um registro de URL + título +
horário, mantido pelo próprio Ultron -- não é o histórico interno do
Chromium/Qt (cookies, senhas, cache continuam onde sempre estiveram,
geridos pelo próprio QtWebEngine). "Apagar a memória dele" (também
pedido explícito) limpa só esta tabela.
"""

from datetime import datetime

from core.database import get_database

_SCHEMA = """
CREATE TABLE IF NOT EXISTS redcore_historico (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    url TEXT NOT NULL,
    titulo TEXT,
    visitado_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_redcore_user ON redcore_historico(user_id);
"""


def _ensure_schema():
    get_database().executescript(_SCHEMA)


def registrar_visita(user_id: str, url: str, titulo: str = ""):
    _ensure_schema()
    if not url or url in ("about:blank", ""):
        return
    get_database().execute(
        "INSERT INTO redcore_historico (user_id, url, titulo, visitado_em) VALUES (?,?,?,?)",
        (user_id, url, titulo or "", datetime.now().isoformat()),
    )


def listar_historico(user_id: str, limit: int = 50) -> list:
    _ensure_schema()
    return get_database().query(
        "SELECT * FROM redcore_historico WHERE user_id=? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    )


def historico_de_hoje(user_id: str) -> list:
    _ensure_schema()
    hoje = datetime.now().strftime("%Y-%m-%d")
    return get_database().query(
        "SELECT * FROM redcore_historico WHERE user_id=? AND visitado_em LIKE ? ORDER BY id DESC",
        (user_id, f"{hoje}%"),
    )


def buscar_historico(user_id: str, termo: str, limit: int = 20) -> list:
    _ensure_schema()
    termo_like = f"%{termo}%"
    return get_database().query(
        "SELECT * FROM redcore_historico WHERE user_id=? AND (url LIKE ? OR titulo LIKE ?) "
        "ORDER BY id DESC LIMIT ?",
        (user_id, termo_like, termo_like, limit),
    )


def limpar_historico(user_id: str) -> int:
    """Apaga TODO o histórico do RedCore deste usuário. Retorna quantas
    visitas foram removidas."""
    _ensure_schema()
    linha = get_database().query_one(
        "SELECT COUNT(*) as n FROM redcore_historico WHERE user_id=?", (user_id,)
    )
    total = linha["n"] if linha else 0
    get_database().execute("DELETE FROM redcore_historico WHERE user_id=?", (user_id,))
    return total
