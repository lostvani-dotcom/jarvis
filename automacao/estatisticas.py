"""
automacao/estatisticas.py
============================
Estatísticas de uso: quantas mensagens o Ultron processou e quais
plugins/recursos mais responderam, num período -- lido do mesmo evento
"message_processed" que core/jarvis.py:process() já grava a CADA
mensagem (ver core/memory.py:events_by_type()). Não precisa de nenhuma
instrumentação nova: o dado já existia, só faltava uma consulta
agregada em cima dele.
"""

import re
from collections import Counter
from datetime import datetime, timedelta

from core.memory import Memory

_PLUGIN_RE = re.compile(r"plugin=(\S+)")

_ROTULOS_AMIGAVEIS = {
    "fallback": "sem resposta reconhecida",
    "conversa": "conversa natural",
    "ia": "IA (conversa aberta)",
    "knowledge_base": "base de conhecimento",
    "knowledge_search": "pesquisa (Wikipedia/web)",
    "comando_nao_reconhecido": "comando não reconhecido",
}


def _rotulo(nome: str) -> str:
    return _ROTULOS_AMIGAVEIS.get(nome, nome)


def resumo(dias: int = 7, top_n: int = 8) -> dict:
    """Agrega os eventos `message_processed` dos últimos `dias` dias:
    total de mensagens, os `top_n` plugins/recursos que mais
    responderam, e uma contagem por dia (pra um gráfico simples do lado
    do cliente, se quiser)."""
    desde = (datetime.now() - timedelta(days=dias)).isoformat()
    eventos = Memory().events_by_type("message_processed", since=desde, limit=20000)

    contagem = Counter()
    por_dia = Counter()
    for ev in eventos:
        m = _PLUGIN_RE.search(ev.get("description") or "")
        plugin = m.group(1) if m else "desconhecido"
        contagem[plugin] += 1
        try:
            dia = datetime.fromisoformat(ev["timestamp"]).strftime("%Y-%m-%d")
            por_dia[dia] += 1
        except (KeyError, ValueError, TypeError):
            pass

    top = [
        {"plugin": nome, "rotulo": _rotulo(nome), "vezes": vezes}
        for nome, vezes in contagem.most_common(top_n)
    ]
    return {
        "total_mensagens": len(eventos),
        "dias": dias,
        "top_comandos": top,
        "por_dia": [{"dia": d, "mensagens": n} for d, n in sorted(por_dia.items())],
    }


def formatar_texto(dias: int = 7) -> str:
    dados = resumo(dias)
    if dados["total_mensagens"] == 0:
        return f"Não processei nenhuma mensagem nos últimos {dias} dia(s)."
    linhas = [f"Nos últimos {dados['dias']} dia(s): {dados['total_mensagens']} mensagem(ns) processada(s)."]
    if dados["top_comandos"]:
        linhas.append("Mais usados:")
        for item in dados["top_comandos"]:
            linhas.append(f"- {item['rotulo']}: {item['vezes']}x")
    return "\n".join(linhas)
