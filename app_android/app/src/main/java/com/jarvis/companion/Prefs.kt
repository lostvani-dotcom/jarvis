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

    // ---- bloqueio do app (só o dono abre, via biometria do celular) ----
    var appLockAtivo: Boolean
        get() = sp.getBoolean("app_lock", false)
        set(value) = sp.edit().putBoolean("app_lock", value).apply()

    // Marca que já perguntamos sobre o bloqueio uma vez (pra não repetir
    // o convite a cada abertura -- só na primeira, ou via botão depois).
    var lockSetupPerguntado: Boolean
        get() = sp.getBoolean("lock_setup_perguntado", false)
        set(value) = sp.edit().putBoolean("lock_setup_perguntado", value).apply()
}
