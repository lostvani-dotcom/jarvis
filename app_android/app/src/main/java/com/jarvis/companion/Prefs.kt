package com.jarvis.companion

import android.content.Context

/** Guarda IP/porta/token do servidor do Ultron (server/http_server.py)
 * localmente no celular, via SharedPreferences. */
class Prefs(context: Context) {
    private val sp = context.getSharedPreferences("jarvis_prefs", Context.MODE_PRIVATE)

    var host: String
        get() = sp.getString("host", "") ?: ""
        set(value) = sp.edit().putString("host", value).apply()

    var port: String
        get() = sp.getString("port", "8765") ?: "8765"
        set(value) = sp.edit().putString("port", value).apply()

    var token: String
        get() = sp.getString("token", "") ?: ""
        set(value) = sp.edit().putString("token", value).apply()

    /** Aceita tanto um IP local quanto uma URL completa (ex.:
     * https://xxxx.trycloudflare.com) no campo "host" -- acesso remoto
     * de fora da rede local (ver server/tunnel.py) usa uma URL do
     * túnel Cloudflare em vez de IP:porta. */
    val baseUrl: String
        get() = if (host.startsWith("http://") || host.startsWith("https://")) host else "http://$host:$port"

    // ---- IA direto na nuvem (conversar sem o PC ligado) ----
    // Preenchidos automaticamente via GET /ia/config quando o app fala
    // com o PC (ver MainActivity.sincronizarIaConfig); depois disso a
    // conversa funciona com o PC desligado, direto com o provedor.
    var iaBaseUrl: String
        get() = sp.getString("ia_base_url", "") ?: ""
        set(value) = sp.edit().putString("ia_base_url", value).apply()

    var iaApiKey: String
        get() = sp.getString("ia_api_key", "") ?: ""
        set(value) = sp.edit().putString("ia_api_key", value).apply()

    var iaModelo: String
        get() = sp.getString("ia_modelo", "") ?: ""
        set(value) = sp.edit().putString("ia_modelo", value).apply()

    var iaAuthHeader: String
        get() = sp.getString("ia_auth_header", "Authorization") ?: "Authorization"
        set(value) = sp.edit().putString("ia_auth_header", value).apply()

    var iaSystemPrompt: String
        get() = sp.getString("ia_system_prompt", "") ?: ""
        set(value) = sp.edit().putString("ia_system_prompt", value).apply()

    val iaConfigurada: Boolean
        get() = iaBaseUrl.isNotEmpty() && iaApiKey.isNotEmpty() && iaModelo.isNotEmpty()

    /** Histórico da conversa na nuvem (CloudAI.kt), serializado como
     * JSON -- PERSISTENTE (sobrevive fechar/reabrir o app), diferente
     * da versão anterior que guardava só em memória e esquecia tudo
     * ao matar o processo. É o que faz "conversar sem o PC" parecer
     * de verdade uma conversa contínua, não uma sessão que reseta toda
     * hora. */
    var iaHistoricoJson: String
        get() = sp.getString("ia_historico", "[]") ?: "[]"
        set(value) = sp.edit().putString("ia_historico", value).apply()

    /** Timestamp (epoch ms) da última vez que a config de IA foi
     * sincronizada com sucesso -- usado pra throttlar re-sincronizações
     * automáticas em segundo plano (ver NotifyListenerService.kt),
     * pra não bater no PC toda hora só pra checar se mudou algo. */
    var iaUltimaSincronizacao: Long
        get() = sp.getLong("ia_ultima_sincronizacao", 0L)
        set(value) = sp.edit().putLong("ia_ultima_sincronizacao", value).apply()

    // ---- widget de tela inicial (ver UltronWidgetProvider.kt) ----
    // Boolean? (tri-estado: nunca checado / online / offline) -- SharedPreferences
    // não tem getBoolean nullable de verdade, então -1/0/1 representa
    // desconhecido/false/true.
    var widgetUltimoStatusOnline: Boolean?
        get() = when (sp.getInt("widget_status_online", -1)) {
            1 -> true
            0 -> false
            else -> null
        }
        set(value) = sp.edit().putInt("widget_status_online", when (value) {
            true -> 1
            false -> 0
            null -> -1
        }).apply()
}
