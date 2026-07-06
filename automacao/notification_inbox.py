"""
automacao/notification_inbox.py
===================================
Caixa de entrada em memória de notificações capturadas pelo app
companion do celular, via `NotificationListenerService` (nativo do
Android -- muito mais confiável que o parsing de `dumpsys` feito em
`dispositivos/adb.py:list_notifications()`, que continua existindo
como fallback pra quem não instalou o app, só com ADB sem fio).

O app manda pro endpoint `POST /notify` do servidor (server/), que
chama `registrar()` aqui. `plugins/instagram.py` lê daqui primeiro, e
só cai pro ADB se não tiver nada mais recente.
"""

import threading
import time

_lock = threading.Lock()
_inbox = []  # [{"pacote": str, "titulo": str, "texto": str, "quando": float}, ...]
_MAX_ITEMS = 200


def registrar(pacote: str, titulo: str, texto: str):
    with _lock:
        _inbox.append({"pacote": pacote, "titulo": titulo, "texto": texto, "quando": time.time()})
        del _inbox[:-_MAX_ITEMS]


def mensagens_de(pacote: str) -> list:
    with _lock:
        return [n for n in _inbox if n.get("pacote") == pacote]


def todas() -> list:
    with _lock:
        return list(_inbox)


def limpar():
    with _lock:
        _inbox.clear()
