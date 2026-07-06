"""
plugins/device_control.py
============================
Controla o celular Android de duas formas complementares:

1. **App companion** (app_android/, preferido pra bateria/abrir
   app/app em primeiro plano): o app já conectado ao Ultron (ver
   server/, automacao/phone_commands.py) executa o pedido localmente
   e devolve o resultado -- não precisa de ADB nem ficar pareando
   nada, só o app aberto no celular.
2. **ADB sem fio** (dispositivos/adb.py, usado por
   pareamento/conexão/desconexão/lista/print de tela): sempre dentro
   da mesma rede local, nunca expõe nada na internet.

Como conectar o ADB (só necessário pra print de tela; bateria/abrir
app/primeiro plano já funcionam com o app sozinho):
    1. No celular: Configurações > Opções do desenvolvedor > Depuração
       sem fio > Parear dispositivo com código.
    2. "pareia o celular <ip>:<porta> <código>" -- IP, porta e código
       de 6 dígitos aparecem na tela de pareamento do celular.
    3. "conecta no celular <ip>:<porta>" -- a porta da tela principal
       de Depuração sem fio (diferente da porta de pareamento, e muda
       toda vez que a depuração sem fio é desligada e religada).

Comandos:
    "conecta no celular <ip>[:porta]" / "pareia o celular <ip>:<porta> <código>"
    "desconecta o celular" / "celulares conectados"
    "abre o whatsapp no celular" / "abre <app> no celular"
    "vê a bateria do celular" / "bateria do celular"
    "o que está aberto no celular" / "que app está rodando no celular"
    "tira um print do celular" / "screenshot do celular"
    "aumenta/diminui/muta o volume do celular"
    "liga/desliga a lanterna do celular"
    "cadê meu celular" / "achar o celular" (toca um alarme alto pra encontrar)
    "espaço/armazenamento do celular"
"""

import datetime
import os
import re

from automacao import tasks
from automacao.notify import notify
from automacao.phone_commands import request_command
from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin
from core.timeline import registrar
from dispositivos import adb

_IP_PORT_RE = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3})(?::(\d{1,5}))?")
_CODE_RE = re.compile(r"\b(\d{6})\b")

_CONNECT_RE = re.compile(r"\bconect[ae]r?\s+(?:no|com o|ao|o)?\s*celular", re.IGNORECASE)
_PAIR_RE = re.compile(r"pare(?:ia|ar)\s+(?:o\s+)?celular", re.IGNORECASE)
_DISCONNECT_RE = re.compile(r"desconect[ae]r?\s+(?:o\s+)?celular", re.IGNORECASE)
_LIST_RE = re.compile(r"(celulares|dispositivos|aparelhos)\s+conectados", re.IGNORECASE)
_OPEN_APP_RE = re.compile(r"abr(?:[ae]|ir)\s+(?:o\s+|a\s+)?(.+?)\s+no\s+celular", re.IGNORECASE)
# "bateria" e "celular" em qualquer ordem ("vê a bateria do celular",
# "celular com quanto de bateria", "quanto de bateria tem o celular").
_BATTERY_RE = re.compile(
    r"\bbateria\b.*\bcelular\b|\bcelular\b.*\bbateria\b", re.IGNORECASE
)
# "print"/"screenshot"/"captura" + "celular" em qualquer ordem --
# checado ANTES do print de tela genérico do system_control.py (este
# plugin carrega primeiro, em ordem alfabética: device < system).
_SCREENSHOT_RE = re.compile(
    r"\b(print|screenshot|captura[r]?)\b.*\bcelular\b|\bcelular\b.*\b(print|screenshot|captura)\b",
    re.IGNORECASE,
)
# "aberto/rodando/primeiro plano" + "celular" em qualquer ordem.
_FOREGROUND_RE = re.compile(
    r"\b(abert[oa]s?|rodando|primeiro plano)\b.*\bcelular\b|\bcelular\b.*\b(abert[oa]s?|rodando|primeiro plano)\b",
    re.IGNORECASE,
)
# "volume" + "celular" em qualquer ordem; a direção (subir/descer/mutar)
# é decidida dentro do handler.
# "volume"+"celular" cobre subir/descer; "mutar" sozinho + "celular"
# também conta -- "muta o celular" é tão natural quanto "muta o volume
# do celular", ninguém precisa mencionar "volume" pra pedir silêncio.
_PHONE_VOLUME_RE = re.compile(
    r"\bvolume\b.*\bcelular\b|\bcelular\b.*\bvolume\b|"
    r"\bmut[ae]\w*\b.*\bcelular\b|\bcelular\b.*\bmut[ae]\w*\b",
    re.IGNORECASE,
)
_VOLUME_UP_WORDS = re.compile(r"\b(aumenta\w*|aumente\w*|sobe|suba|mais alto|maior)\b", re.IGNORECASE)
_VOLUME_DOWN_WORDS = re.compile(r"\b(diminui\w*|abaixa\w*|baixa\w*|mais baixo|menor)\b", re.IGNORECASE)
_VOLUME_MUTE_WORDS = re.compile(r"\b(mut[ae]\w*|sil[êe]ncio|sem som)\b", re.IGNORECASE)
# "lanterna"/"flash" + "celular" em qualquer ordem.
_FLASHLIGHT_RE = re.compile(
    r"\b(lanterna|flash)\b.*\bcelular\b|\bcelular\b.*\b(lanterna|flash)\b", re.IGNORECASE
)
_FLASHLIGHT_OFF_WORDS = re.compile(r"\b(desliga|desligue|apaga|apague|desativa|desative)\w*", re.IGNORECASE)
# achar o celular perdido (toca um alarme alto mesmo no silencioso).
_FIND_PHONE_RE = re.compile(
    r"\b(cad[eê]|ach[ae]r?|encontr[ae]r?)\b.*\bcelular\b|\btoca(?:r)?\s+(?:um\s+)?alarme\b.*\bcelular\b",
    re.IGNORECASE,
)
# "armazenamento"/"espaço" + "celular" em qualquer ordem.
_STORAGE_RE = re.compile(
    r"\b(armazenamento|espaço|espaco)\b.*\bcelular\b|\bcelular\b.*\b(armazenamento|espaço|espaco)\b",
    re.IGNORECASE,
)

# --- Comandos novos (exigem o app companion reconstruído; ver README) ---
# Bateria DETALHADA (saúde/temperatura/voltagem) -- checado ANTES do
# _BATTERY_RE genérico, que só dá o nível.
_BAT_DETALHE_RE = re.compile(
    r"\b(sa[úu]de|temperatura|voltagem|detalhe\w*)\b.*\bbateria\b.*\bcelular\b|"
    r"\bbateria\b.*\bcelular\b.*\b(sa[úu]de|temperatura|voltagem)\b|"
    r"\b(sa[úu]de|temperatura)\s+da\s+bateria\b",
    re.IGNORECASE,
)
_DND_RE = re.compile(
    r"\bn[ãa]o\s+perturbe\b.*\bcelular\b|\bcelular\b.*\bn[ãa]o\s+perturbe\b", re.IGNORECASE
)
_MODO_TOQUE_RE = re.compile(
    r"\b(modo\s+)?(silencios[oa]|vibra[çcr]\w*|toque\s+normal)\b.*\bcelular\b|"
    r"\bcelular\b.*\b(silencios[oa]|vibra[çcr]\w*|modo\s+normal)\b",
    re.IGNORECASE,
)
_BRILHO_CEL_RE = re.compile(
    r"\bbrilho\b.*\bcelular\b|\bcelular\b.*\bbrilho\b", re.IGNORECASE
)
_LOCAL_RE = re.compile(
    r"\b(localiza[çc][ãa]o|onde\s+(fica|est[áa]|ta)|gps)\b.*\bcelular\b|"
    r"\bcelular\b.*\blocaliza[çc][ãa]o\b",
    re.IGNORECASE,
)
_DADOS_RE = re.compile(
    r"\b(consumo\s+de\s+dados|quanto\s+de\s+dados|gasto\s+de\s+dados)\b.*\bcelular\b|"
    r"\bcelular\b.*\bconsumo\s+de\s+dados\b",
    re.IGNORECASE,
)
_REDE_RE = re.compile(
    r"\b(status\s+da\s+rede|conex[ãa]o|rede)\s+do\s+celular\b|"
    r"\bcelular\b.*\bconectad[oa]\s+(em|no|na|via)\b",
    re.IGNORECASE,
)
_NUM_RE = re.compile(r"(\d{1,3})")

# Monitoramento autônomo de bateria: "controla o celular sozinho" --
# em vez de só responder quando perguntado, fica de olho na bateria em
# segundo plano e avisa sozinho quando ela fica baixa.
_MONITOR_BATTERY_RE = re.compile(
    r"\b(monitor[ae]\w*|fica\w*\s+de\s+olho|avis[ae]\w*)\b.*\bbateria\b.*\bcelular\b",
    re.IGNORECASE,
)
_STOP_MONITOR_BATTERY_RE = re.compile(
    r"\bpar[ae]\w*\s+de\s+monitorar\s+a\s+bateria\b", re.IGNORECASE
)
_LIMIAR_BATERIA_BAIXA = 20  # %
_INTERVALO_MONITOR_BATERIA = 900  # 15 minutos

_SEM_APP_NEM_ADB = (
    "Não consegui falar com o celular. Abra o app do Ultron nele (é o jeito mais fácil -- "
    "veja app_android/README.md), ou conecte por ADB sem fio dizendo "
    "'pareia o celular <ip>:<porta> <código>'."
)


class DeviceControlPlugin(BasePlugin):
    name = "device_control"
    description = "Controla o celular Android (via app companion, ou ADB sem fio como alternativa)"

    def matches(self, text: str) -> bool:
        t = text.strip()
        return bool(
            _PAIR_RE.search(t) or _CONNECT_RE.search(t) or _DISCONNECT_RE.search(t)
            or _LIST_RE.search(t) or _OPEN_APP_RE.search(t) or _BATTERY_RE.search(t)
            or _SCREENSHOT_RE.search(t) or _FOREGROUND_RE.search(t) or _PHONE_VOLUME_RE.search(t)
            or _FLASHLIGHT_RE.search(t) or _FIND_PHONE_RE.search(t) or _STORAGE_RE.search(t)
            or _MONITOR_BATTERY_RE.search(t) or _STOP_MONITOR_BATTERY_RE.search(t)
            or _BAT_DETALHE_RE.search(t) or _DND_RE.search(t) or _MODO_TOQUE_RE.search(t)
            or _BRILHO_CEL_RE.search(t) or _LOCAL_RE.search(t) or _DADOS_RE.search(t)
            or _REDE_RE.search(t)
        )

    def handle(self, text: str, context: dict):
        t = text.strip()

        if _STOP_MONITOR_BATTERY_RE.search(t):
            return self._parar_monitorar_bateria(context)
        if _MONITOR_BATTERY_RE.search(t):
            return self._monitorar_bateria(context)

        # Comandos exclusivamente de ADB -- exigem o binário instalado.
        if _PAIR_RE.search(t) or _CONNECT_RE.search(t) or _DISCONNECT_RE.search(t) or _LIST_RE.search(t):
            if not adb.available():
                return Answer(
                    "Preciso do 'adb' (Android SDK Platform Tools) instalado e no PATH pra "
                    "isso -- veja dispositivos/README.md. Bateria, abrir app e ver o que está "
                    "aberto não precisam disso, só do app do celular conectado.",
                    Confidence.GUESS,
                )
            if _PAIR_RE.search(t):
                return self._pair(t)
            if _CONNECT_RE.search(t):
                return self._connect(t)
            if _DISCONNECT_RE.search(t):
                return self._disconnect()
            return self._list()

        # Bateria DETALHADA antes do nível simples (o detalhe é mais específico).
        if _BAT_DETALHE_RE.search(t):
            return self._bateria_detalhada()
        if _DND_RE.search(t):
            ligar = not bool(re.search(r"\b(deslig|desativ|tir[ae])\w*", t, re.IGNORECASE))
            return self._nao_perturbe(ligar)
        if _MODO_TOQUE_RE.search(t):
            return self._modo_toque(t)
        if _BRILHO_CEL_RE.search(t):
            return self._brilho(t)
        if _LOCAL_RE.search(t):
            return self._localizacao()
        if _DADOS_RE.search(t):
            return self._consumo_dados()
        if _REDE_RE.search(t):
            return self._status_rede()

        if _BATTERY_RE.search(t):
            return self._battery()
        if _FOREGROUND_RE.search(t):
            return self._foreground_app()
        if _SCREENSHOT_RE.search(t):
            return self._screenshot()
        if _PHONE_VOLUME_RE.search(t):
            return self._phone_volume(t)
        if _FLASHLIGHT_RE.search(t):
            return self._flashlight(t)
        if _FIND_PHONE_RE.search(t):
            return self._find_phone()
        if _STORAGE_RE.search(t):
            return self._storage()
        m = _OPEN_APP_RE.search(t)
        if m:
            return self._open_app(m.group(1).strip(" .!"))

        return None

    # --- Handlers dos comandos novos (via app companion) ---

    def _bateria_detalhada(self):
        r = request_command("bateria_detalhada", timeout=8)
        if r is None:
            return Answer(_SEM_APP_NEM_ADB, Confidence.GUESS)
        if r.get("erro"):
            return Answer(r["erro"], Confidence.GUESS)
        partes = [f"saúde: {r.get('saude', '?')}"]
        if r.get("nivel") is not None:
            partes.append(f"carga: {r['nivel']}%")
        if r.get("temperatura_c") is not None:
            partes.append(f"temperatura: {r['temperatura_c']}°C")
        if r.get("voltagem_v") is not None:
            partes.append(f"voltagem: {r['voltagem_v']}V")
        if r.get("tecnologia"):
            partes.append(f"tipo: {r['tecnologia']}")
        return Answer("Bateria do celular -- " + ", ".join(partes) + ".", Confidence.CONFIRMED)

    def _nao_perturbe(self, ligar: bool):
        r = request_command("nao_perturbe", {"ligar": ligar}, timeout=8)
        if r is None:
            return Answer(_SEM_APP_NEM_ADB, Confidence.GUESS)
        if r.get("erro"):
            return Answer(r["erro"], Confidence.GUESS)
        return Answer(f"Não Perturbe do celular {'ligado' if ligar else 'desligado'}.", Confidence.CONFIRMED)

    def _modo_toque(self, t):
        low = t.lower()
        if re.search(r"\bsilencios", low):
            modo = "silencioso"
        elif re.search(r"\bvibra", low):
            modo = "vibrar"
        else:
            modo = "normal"
        r = request_command("modo_toque", {"modo": modo}, timeout=8)
        if r is None:
            return Answer(_SEM_APP_NEM_ADB, Confidence.GUESS)
        if r.get("erro"):
            return Answer(r["erro"], Confidence.GUESS)
        return Answer(f"Celular no modo {modo}.", Confidence.CONFIRMED)

    def _brilho(self, t):
        m = _NUM_RE.search(t)
        pct = int(m.group(1)) if m else 50
        r = request_command("brilho", {"percentual": pct}, timeout=8)
        if r is None:
            return Answer(_SEM_APP_NEM_ADB, Confidence.GUESS)
        if r.get("erro"):
            return Answer(r["erro"], Confidence.GUESS)
        return Answer(f"Brilho do celular ajustado para {r.get('percentual', pct)}%.", Confidence.CONFIRMED)

    def _localizacao(self):
        r = request_command("localizacao", timeout=10)
        if r is None:
            return Answer(_SEM_APP_NEM_ADB, Confidence.GUESS)
        if r.get("erro"):
            return Answer(r["erro"], Confidence.GUESS)
        lat, lon = r.get("latitude"), r.get("longitude")
        prec = r.get("precisao_m")
        extra = f" (precisão ~{prec}m)" if prec else ""
        return Answer(
            f"O celular está por volta de {lat}, {lon}{extra}. "
            f"Abrir no mapa: https://maps.google.com/?q={lat},{lon}",
            Confidence.CONFIRMED,
        )

    def _consumo_dados(self):
        r = request_command("consumo_dados", timeout=8)
        if r is None:
            return Answer(_SEM_APP_NEM_ADB, Confidence.GUESS)
        if r.get("erro"):
            return Answer(r["erro"], Confidence.GUESS)
        return Answer(
            f"Consumo de dados do celular nos últimos {r.get('periodo_dias', 30)} dias: "
            f"{r.get('movel_mb', 0)}MB móveis + {r.get('wifi_mb', 0)}MB Wi-Fi.",
            Confidence.CONFIRMED,
        )

    def _status_rede(self):
        r = request_command("status_rede", timeout=8)
        if r is None:
            return Answer(_SEM_APP_NEM_ADB, Confidence.GUESS)
        if r.get("erro"):
            return Answer(r["erro"], Confidence.GUESS)
        internet = "com internet" if r.get("tem_internet") else "sem internet confirmada"
        return Answer(f"O celular está conectado por {r.get('conexao', '?')} ({internet}).", Confidence.CONFIRMED)

    def _pair(self, t):
        ips = _IP_PORT_RE.findall(t)
        codigo_m = _CODE_RE.search(t)
        if not ips or not ips[0][1] or not codigo_m:
            return Answer(
                "Pra parear, me diga o IP:porta de pareamento e o código de 6 dígitos que "
                "aparecem em Opções do desenvolvedor > Depuração sem fio > Parear dispositivo "
                "com código, no celular. Ex.: 'pareia o celular 192.168.0.10:39451 482913'.",
                Confidence.GUESS,
            )
        ip, porta = ips[0]
        try:
            saida = adb.pair(ip, int(porta), codigo_m.group(1))
        except Exception as e:
            return Answer(f"Falha ao parear: {e}", Confidence.GUESS)
        ok = "successfully paired" in saida.lower()
        return Answer(saida or "Pareado.", Confidence.CONFIRMED if ok else Confidence.GUESS)

    def _connect(self, t):
        ips = _IP_PORT_RE.findall(t)
        if not ips:
            return Answer(
                "Preciso do IP do celular pra conectar. Ex.: 'conecta no celular 192.168.0.10:37451' "
                "(a porta aparece na tela de Depuração sem fio e muda toda vez que ela é religada).",
                Confidence.GUESS,
            )
        ip, porta = ips[0]
        porta = int(porta) if porta else 5555
        try:
            saida = adb.connect(ip, porta)
        except Exception as e:
            return Answer(f"Falha ao conectar: {e}", Confidence.GUESS)
        ok = "connected" in saida.lower()
        return Answer(saida or "Conectado.", Confidence.CONFIRMED if ok else Confidence.GUESS)

    def _disconnect(self):
        try:
            saida = adb.disconnect()
        except Exception as e:
            return Answer(f"Falha ao desconectar: {e}", Confidence.GUESS)
        return Answer(saida or "Desconectado.", Confidence.CONFIRMED)

    def _list(self):
        try:
            dispositivos = adb.list_devices()
        except Exception as e:
            return Answer(f"Falha ao listar dispositivos: {e}", Confidence.GUESS)
        if not dispositivos:
            return Answer(
                "Nenhum celular conectado por ADB agora. Diga 'pareia o celular <ip>:<porta> "
                "<código>' pra conectar pela primeira vez.",
                Confidence.CONFIRMED,
            )
        return Answer("Conectado(s) por ADB: " + ", ".join(dispositivos), Confidence.CONFIRMED)

    def _open_app(self, nome):
        resultado = request_command("abrir_app", {"nome": nome}, timeout=10)
        if resultado is not None:
            if resultado.get("erro"):
                return Answer(resultado["erro"], Confidence.GUESS)
            pacote = resultado.get("pacote", nome)
            return Answer(f'Abri "{nome}" no celular ({pacote}).', Confidence.CONFIRMED)

        if adb.available() and adb.list_devices():
            try:
                pacote = adb.open_app(nome)
                return Answer(f'Abri "{nome}" no celular ({pacote}).', Confidence.CONFIRMED)
            except Exception as e:
                return Answer(str(e), Confidence.GUESS)

        return Answer(_SEM_APP_NEM_ADB, Confidence.GUESS)

    def _monitorar_bateria(self, context):
        user_id = context["user_id"]
        routine_name = f"bateria_celular_{user_id}"
        estado = {"ja_avisado": False}

        def _tick():
            resultado = request_command("bateria", timeout=8)
            if resultado is None or resultado.get("nivel") is None:
                return
            nivel = resultado["nivel"]
            if nivel <= _LIMIAR_BATERIA_BAIXA and not resultado.get("carregando") and not estado["ja_avisado"]:
                estado["ja_avisado"] = True
                notify("Ultron", f"A bateria do seu celular está em {nivel}% -- considere carregar.")
                registrar("bateria_celular_baixa", f"{nivel}%")
            elif nivel > _LIMIAR_BATERIA_BAIXA + 10:
                # Só reseta o aviso depois de subir um pouco além do limiar,
                # pra não ficar oscilando aviso/sem-aviso perto do limiar.
                estado["ja_avisado"] = False

        tasks.schedule_recurring(routine_name, _INTERVALO_MONITOR_BATERIA, _tick)
        return Answer(
            f"Combinado, vou checar a bateria do celular a cada {_INTERVALO_MONITOR_BATERIA // 60} "
            f"minutos e te aviso sozinho se ela cair a {_LIMIAR_BATERIA_BAIXA}% ou menos sem estar "
            'carregando. Diga "para de monitorar a bateria" quando quiser parar.',
            Confidence.CONFIRMED,
        )

    def _parar_monitorar_bateria(self, context):
        user_id = context["user_id"]
        routine_name = f"bateria_celular_{user_id}"
        if tasks.cancel_routine(routine_name):
            return Answer("Ok, parei de monitorar a bateria do celular.", Confidence.CONFIRMED)
        return Answer("Eu não estava monitorando a bateria do celular.", Confidence.CONFIRMED)

    def _battery(self):
        resultado = request_command("bateria", timeout=8)
        if resultado is not None and resultado.get("nivel") is not None:
            status = "carregando" if resultado.get("carregando") else "na bateria"
            return Answer(f"O celular está com {resultado['nivel']}% de bateria ({status}).", Confidence.CONFIRMED)

        if adb.available() and adb.list_devices():
            try:
                info = adb.battery_level()
                nivel = info["nivel_percentual"]
                if nivel is not None:
                    status = "carregando" if info["carregando"] else "na bateria"
                    return Answer(f"O celular está com {nivel}% de bateria ({status}).", Confidence.CONFIRMED)
            except Exception:
                pass

        return Answer(_SEM_APP_NEM_ADB, Confidence.GUESS)

    def _foreground_app(self):
        resultado = request_command("primeiro_plano", timeout=8)
        if resultado is None:
            return Answer(_SEM_APP_NEM_ADB, Confidence.GUESS)
        if resultado.get("erro"):
            return Answer(resultado["erro"], Confidence.GUESS)
        app = resultado.get("app") or resultado.get("pacote", "algo que não reconheci")
        return Answer(f'No celular agora está aberto: "{app}".', Confidence.CONFIRMED)

    def _screenshot(self):
        if not adb.available() or not adb.list_devices():
            return Answer(
                "Print do celular ainda só funciona por ADB sem fio (não pelo app). "
                "Diga 'pareia o celular <ip>:<porta> <código>' pra conectar primeiro.",
                Confidence.CONFIRMED,
            )
        pasta = os.path.join("data", "screenshots")
        os.makedirs(pasta, exist_ok=True)
        nome = f"celular_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        caminho = os.path.join(pasta, nome)
        try:
            adb.screenshot(caminho)
        except Exception as e:
            return Answer(f"Falha ao capturar a tela do celular: {e}", Confidence.GUESS)
        return Answer(f"Print do celular salvo em {caminho}.", Confidence.CONFIRMED)

    def _phone_volume(self, t):
        if _VOLUME_MUTE_WORDS.search(t):
            acao, particípio = "mutar", "mutado"
        elif _VOLUME_DOWN_WORDS.search(t):
            acao, particípio = "descer", "diminuído"
        else:
            acao, particípio = "subir", "aumentado"

        resultado = request_command("volume_celular", {"acao": acao}, timeout=8)
        if resultado is None:
            return Answer(_SEM_APP_NEM_ADB, Confidence.GUESS)
        if resultado.get("erro"):
            return Answer(resultado["erro"], Confidence.GUESS)
        return Answer(f"Volume do celular {particípio}.", Confidence.CONFIRMED)

    def _flashlight(self, t):
        ligar = not bool(_FLASHLIGHT_OFF_WORDS.search(t))
        resultado = request_command("lanterna", {"ligar": ligar}, timeout=8)
        if resultado is None:
            return Answer(_SEM_APP_NEM_ADB, Confidence.GUESS)
        if resultado.get("erro"):
            return Answer(resultado["erro"], Confidence.GUESS)
        return Answer(f"Lanterna do celular {'ligada' if ligar else 'desligada'}.", Confidence.CONFIRMED)

    def _find_phone(self):
        resultado = request_command("achar_celular", timeout=8)
        if resultado is None:
            return Answer(_SEM_APP_NEM_ADB, Confidence.GUESS)
        if resultado.get("erro"):
            return Answer(resultado["erro"], Confidence.GUESS)
        return Answer(
            "Tocando um alarme bem alto no celular por alguns segundos, mesmo se estiver no "
            "silencioso -- deve dar pra achar pelo som.",
            Confidence.CONFIRMED,
        )

    def _storage(self):
        resultado = request_command("armazenamento", timeout=8)
        if resultado is None:
            return Answer(_SEM_APP_NEM_ADB, Confidence.GUESS)
        if resultado.get("erro"):
            return Answer(resultado["erro"], Confidence.GUESS)
        livre = resultado.get("livre_gb")
        total = resultado.get("total_gb")
        return Answer(f"O celular tem {livre}GB livres de {total}GB no total.", Confidence.CONFIRMED)
