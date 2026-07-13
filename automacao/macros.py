"""
automacao/macros.py
======================
Macros: uma sequência de comandos já existentes do Ultron, salva sob
um nome, pra rodar tudo de uma vez ("roda a macro <nome>") ou sozinho
em intervalos ("agenda a macro <nome> a cada 30 minutos").

Isto NÃO é "IA decide sozinha o que fazer no PC sem limite nenhum" --
cada passo de uma macro é um comando que o próprio usuário escreveu ao
criar a macro (mesma frase que ele digitaria normalmente), e cada passo
continua passando por TODAS as mesmas regras de segurança de sempre
(confirmação de ações destrutivas, etc. -- ver seguranca/permissions.py).
Agendar uma macro só decide QUANDO os mesmos passos já aprovados rodam,
nunca O QUE roda.

Cada passo é executado via `jarvis.process("/" + passo)` -- reaproveita
o modo de comando direto (ver core/jarvis.py:process()): só dispatch de
plugins, nunca cai na IA/conversa, e avisa claramente se algum passo não
for reconhecido, em vez de tentar adivinhar.

Persistido em SQLite (`core/database.py`) -- `retomar_agendamentos()`
roda no startup do Ultron e reagenda toda macro que tinha um
agendamento ativo, mesma ideia de `automacao/reminders.py:reschedule_pending()`.
"""

import json
from datetime import datetime, timedelta

from automacao import tasks
from core.database import get_database
from core.timeline import registrar
from logs.logger import get_logger

log = get_logger("automacao")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS automacao_macros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    nome TEXT NOT NULL,
    passos TEXT NOT NULL,
    intervalo_segundos INTEGER,
    criado_em TEXT NOT NULL,
    UNIQUE(user_id, nome)
);
"""

_MAX_PASSOS = 20  # teto simples contra macro gigante/infinita por engano


def _ensure_schema():
    get_database().executescript(_SCHEMA)
    try:
        # Migração pra bancos criados antes de hora_diaria existir --
        # CREATE TABLE IF NOT EXISTS não adiciona coluna em tabela já
        # existente, mesmo padrão de automacao/reminders.py.
        get_database().execute("ALTER TABLE automacao_macros ADD COLUMN hora_diaria TEXT")
    except Exception:
        pass  # coluna já existe


def _segundos_ate_proxima_hora(hora: int, minuto: int, agora: datetime = None) -> float:
    """Quantos segundos faltam até a PRÓXIMA vez que o relógio bater
    hora:minuto -- hoje, se ainda não passou, senão amanhã. Mesma
    lógica de automacao/reminders.py:parse_datetime_from_text, isolada
    aqui porque só precisamos do horário do relógio, não de todo o
    parsing de linguagem natural."""
    agora = agora or datetime.now()
    alvo = agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
    if alvo <= agora:
        alvo += timedelta(days=1)
    return (alvo - agora).total_seconds()


def _routine_name(user_id: str, nome: str) -> str:
    return f"macro_{user_id}_{nome}"


def criar_macro(user_id: str, nome: str, passos: list) -> dict:
    _ensure_schema()
    passos = [p.strip() for p in passos if p and p.strip()][:_MAX_PASSOS]
    if not passos:
        raise ValueError("Uma macro precisa de pelo menos um passo.")
    get_database().execute(
        """
        INSERT INTO automacao_macros (user_id, nome, passos, criado_em)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, nome) DO UPDATE SET
            passos = excluded.passos, criado_em = excluded.criado_em
        """,
        (user_id, nome, json.dumps(passos, ensure_ascii=False), datetime.now().isoformat()),
    )
    registrar("macro_criada", f"{nome} ({len(passos)} passo(s))")
    return obter_macro(user_id, nome)


def obter_macro(user_id: str, nome: str) -> dict:
    _ensure_schema()
    row = get_database().query_one(
        "SELECT * FROM automacao_macros WHERE user_id = ? AND nome = ?", (user_id, nome)
    )
    if not row:
        return None
    row["passos"] = json.loads(row["passos"])
    return row


def listar_macros(user_id: str) -> list:
    _ensure_schema()
    rows = get_database().query(
        "SELECT * FROM automacao_macros WHERE user_id = ? ORDER BY nome", (user_id,)
    )
    for r in rows:
        r["passos"] = json.loads(r["passos"])
    return rows


def remover_macro(user_id: str, nome: str) -> bool:
    _ensure_schema()
    macro = obter_macro(user_id, nome)
    if not macro:
        return False
    cancelar_agendamento(user_id, nome)
    get_database().execute(
        "DELETE FROM automacao_macros WHERE user_id = ? AND nome = ?", (user_id, nome)
    )
    return True


def executar_macro(jarvis, user_id: str, nome: str) -> list:
    """Roda cada passo salvo, em ordem, via modo de comando direto
    ("/", ver core/jarvis.py:process()) -- retorna a lista de
    respostas, uma por passo, na mesma ordem."""
    macro = obter_macro(user_id, nome)
    if not macro:
        raise ValueError(f"Não encontrei nenhuma macro chamada '{nome}'.")
    respostas = []
    for passo in macro["passos"]:
        try:
            resposta = jarvis.process("/" + passo)
        except Exception as e:
            resposta = f"[erro no passo '{passo}': {e}]"
            log.warning("erro executando passo de macro '%s': %s", nome, e)
        respostas.append(resposta)
    registrar("macro_executada", nome)
    return respostas


def agendar_macro(jarvis, user_id: str, nome: str, intervalo_segundos: int):
    _ensure_schema()
    if not obter_macro(user_id, nome):
        raise ValueError(f"Não encontrei nenhuma macro chamada '{nome}'.")
    get_database().execute(
        "UPDATE automacao_macros SET intervalo_segundos = ?, hora_diaria = NULL WHERE user_id = ? AND nome = ?",
        (intervalo_segundos, user_id, nome),
    )
    tasks.schedule_recurring(
        _routine_name(user_id, nome), intervalo_segundos, executar_macro, jarvis, user_id, nome
    )
    registrar("macro_agendada", f"{nome} a cada {intervalo_segundos}s")


def agendar_macro_diaria(jarvis, user_id: str, nome: str, hora: int, minuto: int):
    """Agenda uma macro pra rodar sozinha TODO DIA num horário fixo
    ("todo dia às 7h"), diferente de `agendar_macro` (intervalo fixo
    tipo "a cada 30 minutos"). Guarda `hora_diaria` separado de
    `intervalo_segundos` (mesmo os dois preenchidos, intervalo_segundos
    fica sempre 86400 aqui) porque `retomar_agendamentos` precisa saber
    RECALCULAR o atraso até a próxima ocorrência depois de um reinício
    -- um intervalo puro de 86400s reagendado ingenuamente na hora do
    reinício iria "arrastando" o horário a cada vez que o Ultron
    reiniciasse, em vez de continuar sempre às 7h."""
    _ensure_schema()
    if not obter_macro(user_id, nome):
        raise ValueError(f"Não encontrei nenhuma macro chamada '{nome}'.")
    if not (0 <= hora <= 23 and 0 <= minuto <= 59):
        raise ValueError("Horário inválido.")
    hora_texto = f"{hora:02d}:{minuto:02d}"
    get_database().execute(
        "UPDATE automacao_macros SET intervalo_segundos = 86400, hora_diaria = ? WHERE user_id = ? AND nome = ?",
        (hora_texto, user_id, nome),
    )
    atraso = _segundos_ate_proxima_hora(hora, minuto)
    tasks.schedule_recurring(
        _routine_name(user_id, nome), 86400, executar_macro, jarvis, user_id, nome,
        primeiro_delay_segundos=atraso,
    )
    registrar("macro_agendada", f"{nome} todo dia às {hora_texto}")


def cancelar_agendamento(user_id: str, nome: str) -> bool:
    _ensure_schema()
    get_database().execute(
        "UPDATE automacao_macros SET intervalo_segundos = NULL, hora_diaria = NULL WHERE user_id = ? AND nome = ?",
        (user_id, nome),
    )
    return tasks.cancel_routine(_routine_name(user_id, nome))


def retomar_agendamentos(jarvis):
    """Roda uma vez no startup: reagenda toda macro que tinha um
    `intervalo_segundos` ativo antes do último reinício -- mesma ideia
    de automacao/reminders.py:reschedule_pending(). Macros com
    `hora_diaria` recalculam o atraso até a PRÓXIMA ocorrência daquele
    horário (em vez de esperar um intervalo cheio de 86400s a partir do
    reinício, o que faria o horário combinado "andar" a cada reinício)."""
    _ensure_schema()
    for row in get_database().query(
        "SELECT user_id, nome, intervalo_segundos, hora_diaria FROM automacao_macros WHERE intervalo_segundos IS NOT NULL"
    ):
        if row.get("hora_diaria"):
            hora, minuto = (int(p) for p in row["hora_diaria"].split(":"))
            tasks.schedule_recurring(
                _routine_name(row["user_id"], row["nome"]),
                86400, executar_macro, jarvis, row["user_id"], row["nome"],
                primeiro_delay_segundos=_segundos_ate_proxima_hora(hora, minuto),
            )
        else:
            tasks.schedule_recurring(
                _routine_name(row["user_id"], row["nome"]),
                row["intervalo_segundos"], executar_macro, jarvis, row["user_id"], row["nome"],
            )


def iniciar(jarvis):
    try:
        retomar_agendamentos(jarvis)
    except Exception as e:
        log.warning("falha ao retomar agendamentos de macros: %s", e)
