package com.ultron.loja

import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL

/** Um item do catálogo (GET /loja/catalogo, ver server/loja_catalogo.py). */
data class AppEntry(
    val id: String,
    val nome: String,
    val categoria: String,
    val resumo: String,
    val versaoNome: String,
    val versaoCodigo: Int,
    val arquivo: String,
    val tamanhoMb: Double?,
    val disponivel: Boolean,
)

/** Cliente HTTP simples pro servidor do Ultron -- só o necessário pra
 * loja (catálogo + download de .apk), sem lib externa, mesmo padrão
 * do JarvisClient.kt do app Companion. */
object StoreClient {

    class StoreException(message: String) : Exception(message)

    fun status(baseUrl: String): Boolean = try {
        val conn = URL("$baseUrl/status").openConnection() as HttpURLConnection
        conn.connectTimeout = 4000
        conn.readTimeout = 4000
        try {
            conn.responseCode in 200..299
        } finally {
            conn.disconnect()
        }
    } catch (e: Exception) {
        false
    }

    fun catalogo(baseUrl: String): List<AppEntry> {
        val conn = URL("$baseUrl/loja/catalogo").openConnection() as HttpURLConnection
        try {
            conn.connectTimeout = 6000
            conn.readTimeout = 10000
            val status = conn.responseCode
            val stream = if (status in 200..299) conn.inputStream else conn.errorStream
            val texto = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() } ?: "{}"
            if (status !in 200..299) {
                throw StoreException("erro HTTP $status ao buscar o catálogo")
            }
            val apps: JSONArray = JSONObject(texto).optJSONArray("apps") ?: JSONArray()
            return (0 until apps.length()).map { i ->
                val o = apps.getJSONObject(i)
                AppEntry(
                    id = o.optString("id"),
                    nome = o.optString("nome"),
                    categoria = o.optString("categoria"),
                    resumo = o.optString("resumo"),
                    versaoNome = o.optString("versaoNome"),
                    versaoCodigo = o.optInt("versaoCodigo"),
                    arquivo = o.optString("arquivo"),
                    tamanhoMb = if (o.isNull("tamanhoMb")) null else o.optDouble("tamanhoMb"),
                    disponivel = o.optBoolean("disponivel", false),
                )
            }
        } finally {
            conn.disconnect()
        }
    }

    /** Baixa um .apk do catálogo pro cache do app. Bloqueia -- chame
     * numa thread de fundo. */
    fun baixarApk(baseUrl: String, arquivo: String, destino: File) {
        val conn = URL("$baseUrl/loja/apps/$arquivo").openConnection() as HttpURLConnection
        conn.connectTimeout = 8000
        conn.readTimeout = 60000
        try {
            val status = conn.responseCode
            if (status !in 200..299) {
                throw StoreException("erro HTTP $status ao baixar $arquivo")
            }
            conn.inputStream.use { entrada ->
                FileOutputStream(destino).use { saida -> entrada.copyTo(saida) }
            }
        } finally {
            conn.disconnect()
        }
    }
}
