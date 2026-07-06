"""
automacao/phone_commands.py
==============================
Canal de comando PC -> celular: o Ultron pede algo ao celular
(bateria, app em primeiro plano, abrir um app) através da MESMA
conexão HTTP já usada pelo chat/notificações (server/), sem precisar
de ADB sem fio. O app (app_android/) precisa estar aberto no celular,
porque funciona por polling curto -- ver MainActivity.kt.

Fluxo:
  1. Um plugin chama `request_command("bateria")` -- fica bloqueado
     (a chamada é síncrona) até o celular responder ou estourar o
     timeout.
  2. O app do celular, num loop de polling curto (só enquanto está
     aberto), pega o comando pendente via GET /device/commands.
  3. O celular executa localmente (BatteryManager, PackageManager,
     UsageStatsManager) e devolve o resultado via POST /device/result.
  4. `request_command()` acorda com o resultado.

Fila em memória, só o suficiente pra correlacionar pedido/resposta --
não precisa persistir em disco (comandos são efêmeros, de poucos
segundos).
"""

import threading
import uuid

_lock = threading.Lock()
_pendentes = {}   # id -> {"id", "tipo", "params"}
_eventos = {}      # id -> threading.Event
_resultados = {}   # id -> dict


def request_command(tipo: str, params: dict = None, timeout: float = 15.0):
    """Bloqueia até o celular responder ou o timeout estourar. Retorna
    o dict de resultado que o celular mandou, ou None se ninguém
    respondeu a tempo (app fechado, sem rede, etc.)."""
    comando_id = str(uuid.uuid4())
    evento = threading.Event()
    with _lock:
        _pendentes[comando_id] = {"id": comando_id, "tipo": tipo, "params": params or {}}
        _eventos[comando_id] = evento

    recebeu = evento.wait(timeout)
    with _lock:
        _pendentes.pop(comando_id, None)
        _eventos.pop(comando_id, None)
        resultado = _resultados.pop(comando_id, None)

    return resultado if recebeu else None


def pegar_comando_pendente():
    """Chamado pelo endpoint GET /device/commands -- entrega UM
    comando pendente pro celular (ou None se não tiver nenhum) e some
    com ele daqui, então cada comando só é entregue uma vez."""
    with _lock:
        if not _pendentes:
            return None
        comando_id = next(iter(_pendentes))
        return _pendentes.pop(comando_id)


def submeter_resultado(comando_id: str, resultado: dict) -> bool:
    """Chamado pelo endpoint POST /device/result -- acorda quem
    estiver esperando esse comando específico. Retorna False se o
    comando já tinha expirado (timeout) ou não existia."""
    with _lock:
        evento = _eventos.get(comando_id)
        if evento is None:
            return False
        _resultados[comando_id] = resultado
        evento.set()
    return True
