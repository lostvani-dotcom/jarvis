package com.ultron.loja

import android.content.Context

/** Guarda o IP/porta do Ultron descoberto na rede -- namespace de
 * preferências PRÓPRIO desta app (não compartilha com o Companion). */
class Prefs(context: Context) {
    private val sp = context.getSharedPreferences("loja_prefs", Context.MODE_PRIVATE)

    var host: String
        get() = sp.getString("host", "") ?: ""
        set(value) = sp.edit().putString("host", value).apply()

    var port: String
        get() = sp.getString("port", "8765") ?: "8765"
        set(value) = sp.edit().putString("port", value).apply()

    val baseUrl: String
        get() = "http://$host:$port"
}
