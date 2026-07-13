package com.ultron.redcore

import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL

/** Item do catálogo da loja (GET /loja/catalogo, sem autenticação --
 * ver server/loja_catalogo.py), usado aqui só pra autoatualização. */
data class AppEntry(val id: String, val versaoNome: String, val versaoCodigo: Int, val arquivo: String, val disponivel: Boolean)

/** Cliente HTTP simples pro servidor do Ultron -- só o necessário pro
 * RedCore Mobile (autoatualização + sincronizar histórico), mesmo
 * padrão de JarvisClient.kt (Companion) e StoreClient.kt (Loja). */
object RedCoreClient {

    class ClientException(message: String) : Exception(message)

    fun catalogo(baseUrl: String): List<AppEntry> {
        val conn = URL("$baseUrl/loja/catalogo").openConnection() as HttpURLConnection
        try {
            conn.connectTimeout = 6000
            conn.readTimeout = 10000
            val status = conn.responseCode
            val stream = if (status in 200..299) conn.inputStream else conn.errorStream
            val texto = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() } ?: "{}"
            if (status !in 200..299) throw ClientException("erro HTTP $status")
            val apps: JSONArray = JSONObject(texto).optJSONArray("apps") ?: JSONArray()
            return (0 until apps.length()).map { i ->
                val o = apps.getJSONObject(i)
                AppEntry(
                    id = o.optString("id"),
                    versaoNome = o.optString("versaoNome"),
                    versaoCodigo = o.optInt("versaoCodigo"),
                    arquivo = o.optString("arquivo"),
                    disponivel = o.optBoolean("disponivel", false),
                )
            }
        } finally {
            conn.disconnect()
        }
    }

    fun baixarApk(baseUrl: String, arquivo: String, destino: File) {
        val conn = URL("$baseUrl/loja/apps/$arquivo").openConnection() as HttpURLConnection
        conn.connectTimeout = 8000
        conn.readTimeout = 60000
        try {
            val status = conn.responseCode
            if (status !in 200..299) throw ClientException("erro HTTP $status ao baixar $arquivo")
            conn.inputStream.use { entrada ->
                FileOutputStream(destino).use { saida -> entrada.copyTo(saida) }
            }
        } finally {
            conn.disconnect()
        }
    }

    /** Manda uma página visitada pro histórico do Ultron no PC (opt-in,
     * ver Prefs.sincronizarHistorico e server/http_server.py:/redcore/
     * historico) -- guardado lá do mesmo jeito que o RedCore do PC já
     * guarda o próprio histórico (ver automacao/redcore_historico.py). */
    fun enviarHistorico(baseUrl: String, token: String, url: String, titulo: String) {
        val conn = URL("$baseUrl/redcore/historico").openConnection() as HttpURLConnection
        try {
            conn.requestMethod = "POST"
            conn.connectTimeout = 6000
            conn.readTimeout = 10000
            if (token.isNotEmpty()) conn.setRequestProperty("Authorization", "Bearer $token")
            conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            conn.doOutput = true
            val corpo = JSONObject().put("url", url).put("titulo", titulo)
            conn.outputStream.use { it.write(corpo.toString().toByteArray(Charsets.UTF_8)) }
            conn.responseCode // força a requisição a completar
        } finally {
            conn.disconnect()
        }
    }

    /** Favoritos salvos no RedCore do PC (ver automacao/
     * redcore_favoritos.py) -- não opt-in feito diferente do histórico:
     * favoritar é uma ação deliberada e pontual (não navegação passiva
     * registrada o tempo todo), então sincroniza sempre que o PC
     * estiver configurado, sem precisar de um interruptor extra. */
    fun listarFavoritosPC(baseUrl: String, token: String, userId: String): List<Favorito> {
        val conn = URL("$baseUrl/redcore/favoritos?user_id=$userId").openConnection() as HttpURLConnection
        try {
            conn.connectTimeout = 6000
            conn.readTimeout = 10000
            if (token.isNotEmpty()) conn.setRequestProperty("Authorization", "Bearer $token")
            val status = conn.responseCode
            val stream = if (status in 200..299) conn.inputStream else conn.errorStream
            val texto = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() } ?: "{}"
            if (status !in 200..299) throw ClientException("erro HTTP $status")
            val array = JSONObject(texto).optJSONArray("favoritos") ?: JSONArray()
            return (0 until array.length()).map { i ->
                val o = array.getJSONObject(i)
                Favorito(o.optString("titulo"), o.optString("url"))
            }
        } finally {
            conn.disconnect()
        }
    }

    fun sincronizarFavoritoPC(baseUrl: String, token: String, userId: String, url: String, titulo: String, acao: String) {
        val conn = URL("$baseUrl/redcore/favoritos").openConnection() as HttpURLConnection
        try {
            conn.requestMethod = "POST"
            conn.connectTimeout = 6000
            conn.readTimeout = 10000
            if (token.isNotEmpty()) conn.setRequestProperty("Authorization", "Bearer $token")
            conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            conn.doOutput = true
            val corpo = JSONObject().put("url", url).put("titulo", titulo).put("user_id", userId).put("acao", acao)
            conn.outputStream.use { it.write(corpo.toString().toByteArray(Charsets.UTF_8)) }
            conn.responseCode
        } finally {
            conn.disconnect()
        }
    }
}
