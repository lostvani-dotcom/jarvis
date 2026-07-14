"""
plugins/bateria_pc.py
========================
Monitoramento proativo da bateria do PRÓPRIO PC (notebook) -- mesma
ideia do monitor de bateria do celular (ver
plugins/device_control.py:_monitorar_bateria), só que lendo
`psutil.sensors_battery()` direto (mesma fonte que já responde "bateria
do PC" pontualmente, ver plugins/system_control.py) em vez de perguntar
pro celular. Desktops sem bateria (`sensors_battery() is None`) recebem
um aviso claro em vez de "monitorando" algo que nunca vai disparar.

Comandos:
    "monitora a bateria do PC" / "me avisa se a bateria do PC ficar baixa"
    "para de monitorar a bateria do PC"
"""

import re

from automacao import tasks
from automacao.notify import notify
from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin
from core.timeline import registrar

_LIMIAR_BATERIA_BAIXA = 20
_INTERVALO_MONITOR_SEGUNDOS = 300  # 5 minutos

_MONITORAR_RE = re.compile(
    r"\bmonitor[ae]\w*\s+.*\bbateria\s+do\s+pc\b|"
    r"\bme\s+avis[ae]\w*\s+se\s+a\s+bateria\s+do\s+pc\s+ficar\s+baixa\b",
    re.IGNORECASE,
)
_PARAR_RE = re.compile(r"\bpar[ae]\w*\s+de\s+monitorar\s+a\s+bateria\s+do\s+pc\b", re.IGNORECASE)

_NOME_ROTINA = "bateria_pc_monitor"
_estado = {"ja_avisado": False, "ativo": False}


def _ler_bateria():
    try:
        import psutil
        return psutil.sensors_battery()
    except Exception:
        return None


def _tick():
    bat = _ler_bateria()
    if bat is None:
        return
    if bat.percent <= _LIMIAR_BATERIA_BAIXA and not bat.power_plugged and not _estado["ja_avisado"]:
        _estado["ja_avisado"] = True
        notify("Ultron", f"A bateria do PC está em {bat.percent:.0f}% -- considere ligar na tomada.")
        registrar("bateria_pc_baixa", f"{bat.percent:.0f}%")
    elif bat.percent > _LIMIAR_BATERIA_BAIXA + 10 or bat.power_plugged:
        # Reseta com folga acima do limiar (ou assim que ligar na tomada)
        # pra não ficar oscilando aviso/sem-aviso perto do limiar.
        _estado["ja_avisado"] = False


class BateriaPcPlugin(BasePlugin):
    name = "bateria_pc"
    description = "Monitora a bateria do próprio PC e avisa quando ficar baixa"
    triggers = ["monitora a bateria do pc", "para de monitorar a bateria do pc"]

    def matches(self, text: str) -> bool:
        t = text.strip()
        return bool(_MONITORAR_RE.search(t) or _PARAR_RE.search(t))

    def handle(self, text: str, context: dict):
        t = text.strip()

        if _PARAR_RE.search(t):
            parou = tasks.cancel_routine(_NOME_ROTINA)
            _estado["ativo"] = False
            if parou:
                return Answer("Parei de monitorar a bateria do PC.", Confidence.CONFIRMED)
            return Answer("Eu não estava monitorando a bateria do PC.", Confidence.CONFIRMED)

        if _ler_bateria() is None:
            return Answer(
                "Este computador não tem bateria detectável (ou o Windows não a expõe) -- "
                "é um desktop na tomada, não tem o que monitorar.",
                Confidence.CONFIRMED,
            )

        _estado["ativo"] = True
        _estado["ja_avisado"] = False
        tasks.schedule_recurring(_NOME_ROTINA, _INTERVALO_MONITOR_SEGUNDOS, _tick)
        return Answer(
            f"Combinado, vou checar a bateria do PC a cada {_INTERVALO_MONITOR_SEGUNDOS // 60} "
            f"minutos e te aviso sozinho se ela cair a {_LIMIAR_BATERIA_BAIXA}% ou menos sem estar "
            'na tomada. Diga "para de monitorar a bateria do PC" quando quiser parar.',
            Confidence.CONFIRMED,
        )
