"""
automacao/instagram_auto.py
==============================
Envio automático de respostas no Instagram Direct -- SEM revisão sua.

Isso é uma mudança deliberada em relação ao padrão do projeto
(plugins/instagram.py, que só sugere): o usuário foi avisado
explicitamente que automação não-oficial viola os Termos de Uso do
Instagram (risco real de banimento da conta) e que quem recebe a
mensagem não vai saber que está falando com um bot -- e confirmou que
quer isso mesmo assim. Ver plugins/instagram.py para os comandos que
ligam/desligam isso.

Redutores de risco (não eliminam o risco, só reduzem):
- **Desligado por padrão**, mesmo depois dessa confirmação -- precisa
  de um comando explícito ("ativa o envio automático do instagram")
  pra realmente começar a mandar sozinho.
- **Sessão persistente** (Playwright `launch_persistent_context`, perfil
  salvo em data/instagram_browser_profile/): evita logins repetidos,
  que são um dos padrões mais associados a detecção de bot.
- **Atraso humano** antes de enviar (alguns segundos aleatórios), em
  vez de responder instantaneamente.
- **Limite diário de envios** (config `instagram.limite_envios_por_dia`,
  padrão 15) -- passou do limite, para de mandar sozinho e avisa que
  as próximas mensagens precisam de revisão manual.
- **Log de auditoria**: toda mensagem enviada sozinho fica registrada
  na timeline (core/timeline.py, evento "instagram_enviado") com o
  texto exato mandado, pra você conseguir conferir depois.
- Nunca reprocessa a mesma mensagem duas vezes (marca como
  "instagram_processada" na timeline antes de seguir pra próxima).
"""

import random
import time

from automacao.notification_inbox import mensagens_de as inbox_mensagens_de
from automacao import tasks
from automacao.notify import notify
from core.timeline import registrar
from logs.logger import get_logger

log = get_logger("automacao")

_INSTAGRAM_PKG = "com.instagram.android"
_LIMITE_DIARIO_PADRAO = 15
_INTERVALO_POLL = 30  # segundos

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

_perfil_dir = None
_sessao = {}  # mantém playwright/browser/page vivos entre ticks


def available() -> bool:
    return HAS_PLAYWRIGHT


def _system_prompt_sugestao(contexto_extra: str) -> str:
    base = (
        "Você está ajudando a redigir uma resposta de Instagram Direct em nome do "
        "usuário -- você NÃO é o Ultron respondendo aqui, é a própria voz dele. Tom "
        "casual, natural, breve, como uma mensagem de verdade entre pessoas -- nunca "
        "se identifique como assistente ou IA, e não adicione nada além da resposta "
        "em si (sem 'aqui está uma sugestão:' ou aspas)."
    )
    if contexto_extra:
        base += f"\n\nContexto sobre o usuário (pra imitar melhor o estilo dele):\n{contexto_extra}"
    return base


def _garantir_pagina():
    import os
    global _perfil_dir
    if "page" in _sessao:
        return _sessao["page"]
    if not HAS_PLAYWRIGHT:
        raise RuntimeError(
            "Instale 'playwright' (requirements-automacao.txt) e rode "
            "'python -m playwright install chromium' pra eu conseguir usar o Instagram."
        )

    from config.settings import get_settings
    # Pedido explícito do usuário (2026-07-06): conectar pelo Brave do
    # dia a dia dele, reaproveitando a sessão JÁ LOGADA -- em vez de
    # exigir um login novo num perfil isolado. "instagram.usar_perfil_proprio"
    # (false por padrão agora) é a válvula de escape pra voltar ao perfil
    # isolado antigo se isso causar algum problema.
    usar_perfil_proprio = bool(get_settings().get("instagram.usar_perfil_proprio", False))
    if not usar_perfil_proprio:
        try:
            pagina = _garantir_pagina_perfil_pessoal()
            if pagina is not None:
                return pagina
        except Exception as e:
            log.warning(
                "instagram_auto: falha usando o navegador pessoal (%s) -- caindo pro perfil "
                "isolado.", e,
            )
    return _garantir_pagina_perfil_isolado()


def _garantir_pagina_perfil_pessoal():
    """Reaproveita o navegador do dia a dia (Brave/Chrome/Edge) -- se
    você já está logado no Instagram nele, o Ultron cai direto na caixa
    de entrada, sem pedir login de novo. Cópia isolada (não mexe no seu
    perfil real, funciona com o navegador aberto) numa pasta PRÓPRIA
    (não a cópia genérica de navegador_pessoal.py), pra manter a sessão
    do Instagram estável entre uma chamada e outra."""
    import os
    from automacao import navegador_pessoal
    if not navegador_pessoal.available() or not navegador_pessoal.qual_navegador():
        return None
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pasta_copia = os.path.join(base_dir, "data", "instagram_perfil_pessoal_copia")
    contexto, pagina = navegador_pessoal.abrir_logado(
        "https://www.instagram.com/", pasta_copia=pasta_copia, esconder_automacao=True,
    )
    _sessao["pw"] = getattr(contexto, "_ultron_pw", None)
    _sessao["contexto"] = contexto
    _sessao["page"] = pagina
    return pagina


def _garantir_pagina_perfil_isolado():
    """Caminho antigo: perfil Playwright PRÓPRIO do Instagram (não o
    navegador do dia a dia), exigindo login manual na primeira vez.
    Mantido como fallback (config `instagram.usar_perfil_proprio: true`,
    ou se o navegador pessoal não estiver disponível)."""
    import os
    global _perfil_dir
    if _perfil_dir is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _perfil_dir = os.path.join(base_dir, "data", "instagram_browser_profile")
        os.makedirs(_perfil_dir, exist_ok=True)

    from automacao.browser_engine import kwargs_launch
    from config.settings import get_settings
    pw = sync_playwright().start()
    # Diferente de logins_web.py: aqui a preferência por Brave é
    # DESLIGADA por padrão (instagram.preferir_brave, false), mesmo com
    # automacao.preferir_brave=true globalmente. Motivo: reCAPTCHA do
    # Instagram/Google ficou em branco ao logar via Brave (relatado de
    # verdade) -- provavelmente o Shields/proteção de fingerprint do
    # Brave interferindo na renderização do reCAPTCHA. Chromium puro não
    # tem esse problema. Configurável -- "instagram.preferir_brave": true
    # em config.json volta a usar o Brave se quiser tentar de novo.
    preferir_brave = bool(get_settings().get("instagram.preferir_brave", False))
    # Anti-detecção: o captcha da Meta fica em branco/bloqueia quando
    # detecta um navegador AUTOMATIZADO (Playwright expõe
    # `navigator.webdriver=true` e a flag `--enable-automation`, que os
    # sistemas anti-bot do Instagram leem). Esconder esses sinais faz o
    # captcha renderizar e reduz MUITO a chance de ele aparecer -- não
    # elimina (a Meta luta contra automação de propósito), mas é a
    # diferença entre "captcha em branco impossível" e "captcha normal
    # que você resolve na mão".
    contexto = pw.chromium.launch_persistent_context(
        _perfil_dir,
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
        ignore_default_args=["--enable-automation"],
        **kwargs_launch(preferir_brave=preferir_brave),
    )
    try:
        # Zera navigator.webdriver antes de qualquer página carregar --
        # complemento do arg acima, pega os checks feitos via JS.
        contexto.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
    except Exception:
        pass
    pagina = contexto.pages[0] if contexto.pages else contexto.new_page()
    _sessao["pw"] = pw
    _sessao["contexto"] = contexto
    _sessao["page"] = pagina
    return pagina


def _esta_logado(pagina) -> bool:
    pagina.goto("https://www.instagram.com/direct/inbox/", wait_until="domcontentloaded", timeout=20000)
    return "login" not in pagina.url


def conectar_instagram() -> str:
    """Conecta ao Instagram reaproveitando o navegador do dia a dia
    (Brave/Chrome/Edge) -- pedido explícito do usuário (2026-07-06): se
    você já está logado no Instagram nesse navegador, o Ultron cai numa
    cópia dessa sessão e já entra direto, sem pedir login de novo. Se
    não houver sessão ativa (ou o navegador pessoal não estiver
    disponível), abre a página de login DE VERDADE do Instagram -- você
    digita usuário/senha/2FA direto com o Instagram, o Ultron nunca vê
    nem guarda essa senha (mesmo princípio de
    automacao/logins_web.py:conectar_google()). Uma vez logado, a sessão
    persiste pras próximas vezes (ler mensagens, e responder sozinho se
    instagram.envio_automatico estiver ligado)."""
    pagina = _garantir_pagina()
    if _esta_logado(pagina):
        registrar("instagram_conectado", "")
        return (
            "Já estou conectado -- reaproveitei a sessão logada do seu navegador do dia a dia, "
            "então nem precisou de login. Posso ler suas mensagens, e responder sozinho também, "
            "se você ligar o envio automático."
        )
    pagina.goto("https://www.instagram.com/accounts/login/", wait_until="domcontentloaded", timeout=20000)
    registrar("instagram_conectado", "")
    dica_navegador_aberto = ""
    if getattr(pagina.context, "_usou_perfil_real", True) is False:
        # Não achou login numa CÓPIA do perfil (navegador estava aberto) --
        # bem possível que você esteja logado de verdade, só que a sessão
        # mais recente ainda não tinha sido gravada em disco no momento da
        # cópia (ver navegador_pessoal.py). Fechar o navegador e pedir de
        # novo usa a pasta real direto, sem essa limitação.
        dica_navegador_aberto = (
            " Se você já está logado no Instagram no seu navegador, tente fechá-lo e "
            'pedir "conecta minha conta do instagram" de novo -- com ele fechado eu uso '
            "o perfil real direto, sem risco de perder uma sessão recém-criada."
        )
    return (
        "Abri a página de login do Instagram numa aba -- faça login você mesmo (usuário, "
        "senha, verificação em duas etapas) direto com o Instagram; eu não vejo nem guardo "
        "sua senha. A sessão fica salva pra próxima vez. Depois de logar, posso ler suas "
        "mensagens, e responder sozinho também, se você ligar o envio automático."
        + dica_navegador_aberto
    )


def enviar_resposta(destinatario: str, texto: str) -> None:
    """Abre a conversa com `destinatario` no Instagram Direct e envia
    `texto` -- sem confirmação, chamado só pelo tick automático (ver
    _tick) quando instagram.envio_automatico estiver ligado. Exige que
    a sessão já esteja autenticada via conectar_instagram() -- nunca
    guarda nem digita a senha por conta própria."""
    pagina = _garantir_pagina()
    if not _esta_logado(pagina):
        raise RuntimeError(
            'Não estou logado no Instagram ainda. Diga "conecta minha conta do instagram" '
            "primeiro -- você faz o login direto, eu nunca vejo sua senha."
        )

    pagina.locator(f'text="{destinatario}"').first.click(timeout=10000)

    caixa_texto = pagina.locator('textarea[placeholder], div[contenteditable="true"][aria-label]').first
    caixa_texto.wait_for(timeout=10000)
    time.sleep(random.uniform(1.5, 4.0))  # atraso "humano" antes de digitar
    caixa_texto.fill(texto)
    caixa_texto.press("Enter")
    time.sleep(1.0)


def _limite_diario(jarvis) -> int:
    return int(jarvis.settings.get("instagram.limite_envios_por_dia", _LIMITE_DIARIO_PADRAO))


def _envios_nas_ultimas_24h(memory) -> int:
    """Usa events_by_type() (filtra por tipo DIRETO no SQL), não
    recent_events(limit=N) -- este último pega os últimos N eventos de
    QUALQUER tipo (todos os módulos escrevem na mesma tabela), então um
    dia ativo de visao_continua/habitos/macros podia empurrar eventos
    de "instagram_enviado" antigos pra fora da janela e SUBCONTAR os
    envios do dia, deixando o limite diário furar."""
    from datetime import datetime, timedelta
    desde = datetime.now() - timedelta(hours=24)
    eventos = memory.events_by_type("instagram_enviado", since=desde.isoformat(), limit=1000)
    return len(eventos)


def _ja_processada(memory, chave: str) -> bool:
    """Mesmo motivo de _envios_nas_ultimas_24h: filtra por tipo direto
    no SQL, pra "instagram_processada" nunca ficar invisível atrás de
    eventos de outros módulos e fazer a mesma mensagem ser reprocessada/
    reenviada sozinha."""
    eventos = memory.events_by_type("instagram_processada", limit=2000)
    return any(ev.get("description") == chave for ev in eventos)


def _tick(jarvis):
    if not jarvis.settings.get("instagram.envio_automatico", False):
        return
    if jarvis.ia_manager is None:
        return

    mensagens = inbox_mensagens_de(_INSTAGRAM_PKG)
    for msg in mensagens:
        texto = msg.get("texto")
        titulo = msg.get("titulo") or "alguém"
        if not texto:
            continue
        chave = f"{titulo}::{texto}"
        if _ja_processada(jarvis.memory, chave):
            continue

        if _envios_nas_ultimas_24h(jarvis.memory) >= _limite_diario(jarvis):
            registrar("instagram_processada", chave)
            notify(
                "Ultron",
                "Atingi o limite diário de respostas automáticas no Instagram -- "
                f'a mensagem de "{titulo}" ficou sem resposta automática, revise manualmente.',
            )
            continue

        contexto_extra = jarvis.memory.get_context_summary(jarvis.user_id)
        try:
            _, sugestao = jarvis.ia_manager.chat(
                f'Mensagem recebida no Instagram de "{titulo}": "{texto}"',
                history=[], system_prompt=_system_prompt_sugestao(contexto_extra),
            )
        except Exception as e:
            log.warning("instagram_auto: falha ao gerar sugestão: %s", e)
            continue
        if not sugestao:
            continue

        registrar("instagram_processada", chave)
        try:
            enviar_resposta(titulo, sugestao.strip())
        except Exception as e:
            log.warning("instagram_auto: falha ao enviar resposta: %s", e)
            notify("Ultron", f'Tentei responder "{titulo}" no Instagram sozinho, mas falhou: {e}')
            continue

        registrar("instagram_enviado", f'{titulo}: "{sugestao.strip()[:80]}"')
        notify("Ultron (Instagram automático)", f'Respondi "{titulo}" sozinho: "{sugestao.strip()[:120]}"')


def iniciar(jarvis):
    """Chamado no startup do Ultron -- só agenda o polling se
    instagram.envio_automatico já estiver true (ligado numa sessão
    anterior). Ativar pela primeira vez (plugins/instagram.py) também
    agenda na hora, sem precisar reiniciar."""
    if not jarvis.settings.is_module_enabled("automacao"):
        return
    if not jarvis.settings.get("instagram.envio_automatico", False):
        return
    tasks.schedule_recurring("instagram_auto", _INTERVALO_POLL, _tick, jarvis)
