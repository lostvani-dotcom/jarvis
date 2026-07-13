package com.jarvis.companion

import android.os.Handler
import android.os.Looper
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import org.json.JSONObject
import kotlin.concurrent.thread

/**
 * Dois papéis, os dois rodando com o app FECHADO (é um serviço do
 * sistema, ligado o tempo todo enquanto o acesso a notificações
 * estiver concedido -- diferente de MainActivity, que só existe
 * enquanto a tela está aberta):
 *
 * 1. Encaminha notificações de apps de mensagem pro servidor do
 *    Jarvis (POST /notify), pra plugins/instagram.py sugerir
 *    respostas.
 * 2. Responde aos comandos que o Ultron pede (bateria, abrir app,
 *    app em primeiro plano -- ver DeviceCommands.kt), num loop de
 *    polling curto -- isso é o que faz "vê a bateria do celular"
 *    funcionar mesmo com o app fechado.
 *
 * Exige permissão manual do usuário (Configurações > Apps > Acesso
 * especial > Acesso a notificações -- o botão "Notificações" na tela
 * principal do app abre direto essa tela). Em alguns aparelhos
 * (principalmente Xiaomi/Huawei/Samsung com otimização de bateria
 * agressiva), o sistema pode encerrar o serviço mesmo assim -- se os
 * comandos pararem de responder depois de um tempo, desative a
 * otimização de bateria pro app "Ultron" nas configurações do
 * aparelho.
 *
 * 3. Re-sincroniza a config do "modo nuvem" (CloudAI.kt) em segundo
 *    plano, throttlado (ver INTERVALO_RESYNC_NUVEM_MS) -- assim o
 *    modo nuvem se mantém atualizado (chave/modelo/personalidade)
 *    mesmo em dias que o usuário nunca abre o MainActivity, contanto
 *    que o celular passe pela mesma Wi-Fi do PC em algum momento.
 */
class NotifyListenerService : NotificationListenerService() {

    private val pacotesRelevantes = setOf(
        "com.instagram.android",
        "com.whatsapp",
        "com.facebook.orca",
        "org.telegram.messenger",
        "org.thoughtcrime.securesms", // Signal
        "com.discord",
        "com.google.android.apps.messaging", // Mensagens (SMS/RCS) do Google
    )

    private val pollingHandler = Handler(Looper.getMainLooper())
    private val pollingIntervalMs = 3000L
    private val intervaloResyncNuvemMs = 15 * 60 * 1000L  // 15min -- não vale a pena checar mais que isso
    private var pollingAtivo = false

    private val pollingRunnable = object : Runnable {
        override fun run() {
            if (!pollingAtivo) return
            val prefs = Prefs(applicationContext)
            if (prefs.host.isNotEmpty() && prefs.token.isNotEmpty()) {
                thread {
                    processarComandoPendente(prefs)
                    processarMensagensPendentes(prefs)
                    resincronizarNuvemSeNecessario(prefs)
                }
            }
            pollingHandler.postDelayed(this, pollingIntervalMs)
        }
    }

    /** Só busca GET /ia/config de novo se já faz tempo desde a última
     * sincronização -- sem esse throttle, bateria toda checagem de
     * 3 segundos do polling normal também tentaria isso, o que seria
     * bater no PC à toa pra uma config que quase nunca muda. */
    private fun resincronizarNuvemSeNecessario(prefs: Prefs) {
        val agora = System.currentTimeMillis()
        if (agora - prefs.iaUltimaSincronizacao < intervaloResyncNuvemMs) return
        try {
            val cfg = JarvisClient.getIaConfig(prefs.baseUrl, prefs.token) ?: return
            prefs.iaBaseUrl = cfg.optString("base_url", "")
            prefs.iaApiKey = cfg.optString("api_key", "")
            prefs.iaModelo = cfg.optString("modelo", "")
            prefs.iaAuthHeader = cfg.optString("auth_header", "Authorization")
            prefs.iaSystemPrompt = cfg.optString("system_prompt", "")
            prefs.iaUltimaSincronizacao = agora
        } catch (e: Exception) {
            // melhor-esforço -- tenta de novo no próximo ciclo throttlado
        }
    }

    override fun onListenerConnected() {
        super.onListenerConnected()
        pollingAtivo = true
        pollingHandler.post(pollingRunnable)
    }

    override fun onListenerDisconnected() {
        super.onListenerDisconnected()
        pollingAtivo = false
        pollingHandler.removeCallbacks(pollingRunnable)
    }

    private fun processarComandoPendente(prefs: Prefs) {
        try {
            val comando = JarvisClient.getDeviceCommand(prefs.baseUrl, prefs.token) ?: return
            val id = comando.getString("id")
            val tipo = comando.getString("tipo")
            val params = comando.optJSONObject("params") ?: JSONObject()
            val resultado = DeviceCommands.executar(applicationContext, tipo, params)
            JarvisClient.postDeviceResult(prefs.baseUrl, prefs.token, id, resultado)
        } catch (e: Exception) {
            // melhor-esforço -- só tenta de novo no próximo ciclo
        }
    }

    private fun processarMensagensPendentes(prefs: Prefs) {
        try {
            val mensagens = JarvisClient.poll(prefs.baseUrl, prefs.token)
            for (i in 0 until mensagens.length()) {
                val msg = mensagens.getJSONObject(i)
                val titulo = msg.optString("titulo", "Ultron")
                val texto = msg.optString("mensagem", "")
                if (texto.isNotEmpty()) {
                    NotificacaoLocal.mostrar(applicationContext, titulo, texto)
                }
            }
        } catch (e: Exception) {
            // melhor-esforço
        }
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        val pacote = sbn.packageName
        if (pacote !in pacotesRelevantes) return

        val extras = sbn.notification.extras
        val titulo = extras.getCharSequence("android.title")?.toString() ?: return
        val texto = (extras.getCharSequence("android.bigText") ?: extras.getCharSequence("android.text"))
            ?.toString() ?: return

        val prefs = Prefs(applicationContext)
        if (prefs.host.isEmpty() || prefs.token.isEmpty()) return

        thread {
            try {
                JarvisClient.notify(prefs.baseUrl, prefs.token, pacote, titulo, texto)
            } catch (e: Exception) {
                // melhor-esforço: uma falha de rede pontual não derruba o listener
            }
        }
    }
}
