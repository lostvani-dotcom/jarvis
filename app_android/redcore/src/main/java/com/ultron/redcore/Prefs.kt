package com.ultron.redcore

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

data class Favorito(val titulo: String, val url: String)

/** Conexão com o Ultron do PC (pra autoatualização e sincronização de
 * histórico -- ver server/http_server.py), favoritos e a opção de
 * sincronizar histórico, tudo local via SharedPreferences. Mesmo
 * padrão de app_android/app/.../Prefs.kt e app_android/loja/.../Prefs.kt. */
class Prefs(context: Context) {
    private val sp = context.getSharedPreferences("redcore_prefs", Context.MODE_PRIVATE)

    var host: String
        get() = sp.getString("host", "") ?: ""
        set(value) = sp.edit().putString("host", value).apply()

    var port: String
        get() = sp.getString("port", "8765") ?: "8765"
        set(value) = sp.edit().putString("port", value).apply()

    var token: String
        get() = sp.getString("token", "") ?: ""
        set(value) = sp.edit().putString("token", value).apply()

    val baseUrl: String
        get() = if (host.startsWith("http://") || host.startsWith("https://")) host else "http://$host:$port"

    /** Desligado por padrão -- ver server/http_server.py:/redcore/historico
     * e a decisão de projeto de manter isso opt-in (histórico de
     * navegação é dado sensível, diferente de "qual app instalar"). */
    var sincronizarHistorico: Boolean
        get() = sp.getBoolean("sincronizar_historico", false)
        set(value) = sp.edit().putBoolean("sincronizar_historico", value).apply()

    // ---- Favoritos (só neste celular -- ver MainActivity.alternarFavorito) ----

    var favoritosJson: String
        get() = sp.getString("favoritos", "[]") ?: "[]"
        set(value) = sp.edit().putString("favoritos", value).apply()

    fun listarFavoritos(): List<Favorito> {
        val array = try {
            JSONArray(favoritosJson)
        } catch (e: Exception) {
            JSONArray()
        }
        return (0 until array.length()).map { i ->
            val o = array.getJSONObject(i)
            Favorito(o.optString("titulo"), o.optString("url"))
        }
    }

    fun salvarFavoritos(favoritos: List<Favorito>) {
        val array = JSONArray()
        for (f in favoritos) {
            array.put(JSONObject().put("titulo", f.titulo).put("url", f.url))
        }
        favoritosJson = array.toString()
    }

    fun ehFavorito(url: String): Boolean = listarFavoritos().any { it.url == url }

    fun alternarFavorito(titulo: String, url: String): Boolean {
        val atuais = listarFavoritos().toMutableList()
        val existente = atuais.indexOfFirst { it.url == url }
        val agoraFavorito: Boolean
        if (existente >= 0) {
            atuais.removeAt(existente)
            agoraFavorito = false
        } else {
            atuais.add(0, Favorito(titulo.ifBlank { url }, url))
            agoraFavorito = true
        }
        salvarFavoritos(atuais)
        return agoraFavorito
    }

    fun removerFavoritos(urls: Set<String>) {
        salvarFavoritos(listarFavoritos().filterNot { it.url in urls })
    }
}
