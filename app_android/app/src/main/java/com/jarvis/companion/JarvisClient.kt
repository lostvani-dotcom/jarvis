package com.jarvis.companion

import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

/** Cliente HTTP simples pro servidor do Ultron (server/http_server.py)
 * -- sem lib externa (OkHttp/Retrofit), só java.net puro, porque os
 * endpoints são poucos e simples o bastante pra não precisar disso. */
object JarvisClient {

    class JarvisException(message: String) : Exception(message)

    private fun request(
        baseUrl: String, path: String, method: String, token: String, body: JSONObject? = null,
    ): JSONObject {
        val conn = URL(baseUrl + path).openConnection() as HttpURLConnection
        try {
            conn.requestMethod = method
            conn.connectTimeout = 8000
            conn.readTimeout = 30000
            if (token.isNotEmpty()) {
                conn.setRequestProperty("Authorization", "Bearer $token")
            }
            if (body != null) {
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            }

            val status = conn.responseCode
            val stream = if (status in 200..299) conn.inputStream else conn.errorStream
            val texto = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() } ?: "{}"
            val json = try {
                JSONObject(texto)
            } catch (e: Exception) {
                JSONObject()
            }

            if (status !in 200..299) {
                throw JarvisException(json.optString("erro", "erro HTTP $status"))
            }
            return json
        } finally {
            conn.disconnect()
        }
    }

    fun status(baseUrl: String): Boolean = try {
        request(baseUrl, "/status", "GET", "").optBoolean("ok", false)
    } catch (e: Exception) {
        false
    }

    /** Config do provedor de IA (URL/chave/modelo/prompt) pra conversar
     * direto com a nuvem quando o PC estiver desligado -- ver
     * server/http_server.py:/ia/config. Null se o PC não tiver provedor
     * remoto configurado (ou a chamada falhar). */
    fun getIaConfig(baseUrl: String, token: String): JSONObject? = try {
        val r = request(baseUrl, "/ia/config", "GET", token)
        if (r.optBoolean("disponivel", false)) r else null
    } catch (e: Exception) {
        null
    }

    fun chat(baseUrl: String, token: String, texto: String): String {
        val body = JSONObject().put("text", texto)
        return request(baseUrl, "/chat", "POST", token, body).optString("resposta", "")
    }

    fun notify(baseUrl: String, token: String, pacote: String, titulo: String, texto: String) {
        val body = JSONObject()
            .put("pacote", pacote)
            .put("titulo", titulo)
            .put("texto", texto)
        request(baseUrl, "/notify", "POST", token, body)
    }

    /** Pergunta se o Ultron pediu algo (bateria, abrir app, app em
     * primeiro plano) -- ver automacao/phone_commands.py. Retorna
     * null se não tiver nada pendente agora. */
    fun getDeviceCommand(baseUrl: String, token: String): JSONObject? {
        val resposta = request(baseUrl, "/device/commands", "GET", token)
        return resposta.optJSONObject("comando")
    }

    fun postDeviceResult(baseUrl: String, token: String, id: String, resultado: JSONObject) {
        val body = JSONObject().put("id", id).put("resultado", resultado)
        request(baseUrl, "/device/result", "POST", token, body)
    }

    /** Mensagens espontâneas do Ultron (lembrete, comentário de
     * observação -- ver automacao/notify.py). */
    fun poll(baseUrl: String, token: String): JSONArray {
        return request(baseUrl, "/poll", "GET", token).optJSONArray("mensagens") ?: JSONArray()
    }

    /** Versão do APK disponível no PC (ver server/http_server.py,
     * GET /app/version) -- sem autenticação, é só metadado público
     * pra decidir se vale baixar uma atualização. */
    fun getServerVersion(baseUrl: String): JSONObject = request(baseUrl, "/app/version", "GET", "")

    /** POST de corpo binário puro (áudio/imagem), separado de `request`
     * porque esses endpoints não recebem/devolvem um JSON no corpo da
     * REQUISIÇÃO (só na resposta) -- ver server/http_server.py,
     * POST /voz/amostra e POST /visao/identificar. */
    private fun requestBinario(
        baseUrl: String, path: String, token: String, contentType: String, corpo: ByteArray,
    ): JSONObject {
        val conn = URL(baseUrl + path).openConnection() as HttpURLConnection
        try {
            conn.requestMethod = "POST"
            conn.connectTimeout = 8000
            conn.readTimeout = 30000
            if (token.isNotEmpty()) conn.setRequestProperty("Authorization", "Bearer $token")
            conn.setRequestProperty("Content-Type", contentType)
            conn.doOutput = true
            conn.outputStream.use { it.write(corpo) }

            val status = conn.responseCode
            val stream = if (status in 200..299) conn.inputStream else conn.errorStream
            val texto = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() } ?: "{}"
            val json = try {
                JSONObject(texto)
            } catch (e: Exception) {
                JSONObject()
            }
            if (status !in 200..299) {
                throw JarvisException(json.optString("erro", "erro HTTP $status"))
            }
            return json
        } finally {
            conn.disconnect()
        }
    }

    /** Envia uma amostra de voz gravada no celular pro PC usar na
     * clonagem de voz (ver voz/clonagem.py:salvar_amostra_upload). O
     * arquivo já vem no formato do MediaRecorder (.m4a/MPEG-4 + AAC). */
    fun enviarAmostraVoz(baseUrl: String, token: String, arquivo: File) {
        requestBinario(baseUrl, "/voz/amostra", token, "audio/mp4", arquivo.readBytes())
    }

    /** Manda uma foto (JPEG) pro reconhecimento facial do PC (LBPH, ver
     * visao/faces.py) e devolve os rostos identificados, cada um com
     * "nome" e "confianca". Lista vazia = nenhum rosto reconhecido. */
    fun identificarRosto(baseUrl: String, token: String, jpegBytes: ByteArray): JSONArray {
        val resposta = requestBinario(baseUrl, "/visao/identificar", token, "image/jpeg", jpegBytes)
        return resposta.optJSONArray("rostos") ?: JSONArray()
    }

    /** Baixa um screenshot cru (JPEG) da tela do PC agora -- ver
     * server/http_server.py:/tela/atual e visao/screen.py. Usado pela
     * tela "Ver tela do PC" (ScreenViewActivity), via polling curto. */
    fun getScreenshot(baseUrl: String, token: String): ByteArray {
        val conn = URL("$baseUrl/tela/atual").openConnection() as HttpURLConnection
        try {
            conn.connectTimeout = 6000
            conn.readTimeout = 10000
            if (token.isNotEmpty()) conn.setRequestProperty("Authorization", "Bearer $token")
            val status = conn.responseCode
            if (status !in 200..299) {
                val erro = conn.errorStream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() } ?: ""
                throw JarvisException("erro HTTP $status $erro")
            }
            return conn.inputStream.use { it.readBytes() }
        } finally {
            conn.disconnect()
        }
    }

    /** Estatísticas de uso agregadas (ver automacao/estatisticas.py e
     * server/http_server.py:/estatisticas) -- total de mensagens
     * processadas e os plugins/recursos que mais responderam, num
     * período de `dias` dias. */
    fun getEstatisticas(baseUrl: String, token: String, dias: Int = 7): JSONObject {
        return request(baseUrl, "/estatisticas?dias=$dias", "GET", token)
    }
}
