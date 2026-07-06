"""
automacao/redcore_historico.py
==================================
Histórico de navegação do RedCore (gui/redcore.py, o navegador do
Ultron) -- URL + título + CONTEÚDO DE TEXTO da página são registrados
aqui, pra o Ultron "ver tudo que você usa" (pedido explícito do
usuário, incluindo e-mails e qualquer outra coisa que apareça na tela
do navegador) e responder coisas como "o que eu vi hoje" / "o que
dizia aquele e-mail sobre X".

Honesto sobre o escopo e os riscos:
- Captura o TEXTO VISÍVEL da página (via QWebEngineView.page().toPlainText()),
  não elementos ocultos, não o que está atrás de login que o próprio
  QtWebEngine não carregou, e não anexos/imagens.
- Webmail (Gmail, Outlook) costuma ser uma SPA -- trocar de e-mail na
  caixa de entrada muitas vezes NÃO muda a URL nem dispara um novo
  carregamento de página. Por isso gui/redcore.py também tira uma
  "foto" do texto periodicamente (não só ao navegar) -- é o único jeito
  de pegar o conteúdo de um e-mail aberto sem uma URL nova.
- Esse conteúdo fica em TEXTO PURO no banco local (data/jarvis.db, já
  fora do git via .gitignore) -- não está criptografado. "Apagar a
  memória dele" (comando "apaga o histórico do redcore") apaga tudo
  isso, sem exceção.
- Nunca tenta ler senhas salvas, cookies ou qualquer coisa da área
  protegida do próprio navegador -- só o que está renderizado na tela.
"""

from datetime import datetime

from core.database import get_database

_SCHEMA = """
CREATE TABLE IF NOT EXISTS redcore_historico (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    url TEXT NOT NULL,
    titulo TEXT,
    conteudo_texto TEXT,
    visitado_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_redcore_user ON redcore_historico(user_id);
"""

_MAX_CONTEUDO_CHARS = 20000  # generoso (cobre e-mails/páginas inteiras), mas com teto


def _ensure_schema():
    get_database().executescript(_SCHEMA)
    # Migração leve: bancos criados pela versão anterior (sem
    # conteudo_texto) ganham a coluna sem perder as visitas já
    # registradas -- ALTER TABLE ADD COLUMN é seguro de repetir (ignora
    # se a coluna já existir).
    try:
        get_database().execute("ALTER TABLE redcore_historico ADD COLUMN conteudo_texto TEXT")
    except Exception:
        pass  # coluna já existe


def registrar_visita(user_id: str, url: str, titulo: str = "", conteudo: str = "") -> int:
    """Registra uma visita (navegação nova). Retorna o id da linha --
    quem chama pode usar isso pra depois ATUALIZAR o conteúdo da MESMA
    visita conforme a página carrega/muda (ver atualizar_conteudo)."""
    _ensure_schema()
    if not url or url in ("about:blank", ""):
        return -1
    conteudo = (conteudo or "")[:_MAX_CONTEUDO_CHARS]
    cursor = get_database().execute(
        "INSERT INTO redcore_historico (user_id, url, titulo, conteudo_texto, visitado_em) "
        "VALUES (?,?,?,?,?)",
        (user_id, url, titulo or "", conteudo, datetime.now().isoformat()),
    )
    return cursor.lastrowid


def atualizar_conteudo(visita_id: int, titulo: str = None, conteudo: str = None):
    """Atualiza título/conteúdo de uma visita JÁ registrada -- usado
    pelas capturas periódicas (mesma URL/aba, conteúdo mudou sem
    navegação nova, ex.: trocar de e-mail numa SPA)."""
    if visita_id is None or visita_id < 0:
        return
    _ensure_schema()
    campos, valores = [], []
    if titulo is not None:
        campos.append("titulo=?")
        valores.append(titulo)
    if conteudo is not None:
        campos.append("conteudo_texto=?")
        valores.append((conteudo or "")[:_MAX_CONTEUDO_CHARS])
    if not campos:
        return
    valores.append(visita_id)
    get_database().execute(f"UPDATE redcore_historico SET {', '.join(campos)} WHERE id=?", tuple(valores))


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
    """Busca por URL, título OU conteúdo da página -- é o que permite
    achar 'aquele e-mail que falava sobre X', não só páginas cujo
    título/URL menciona X."""
    _ensure_schema()
    termo_like = f"%{termo}%"
    return get_database().query(
        "SELECT * FROM redcore_historico WHERE user_id=? AND "
        "(url LIKE ? OR titulo LIKE ? OR conteudo_texto LIKE ?) ORDER BY id DESC LIMIT ?",
        (user_id, termo_like, termo_like, termo_like, limit),
    )


def limpar_historico(user_id: str) -> int:
    """Apaga TODO o histórico do RedCore deste usuário (URLs, títulos E
    conteúdo de texto capturado). Retorna quantas visitas foram
    removidas."""
    _ensure_schema()
    linha = get_database().query_one(
        "SELECT COUNT(*) as n FROM redcore_historico WHERE user_id=?", (user_id,)
    )
    total = linha["n"] if linha else 0
    get_database().execute("DELETE FROM redcore_historico WHERE user_id=?", (user_id,))
    return total
