package com.jarvis.companion

import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * Conversa DIRETO com o provedor de IA (formato OpenAI chat/completions,
 * mesmo protocolo de ia/providers/openai_compatible.py do PC) -- é o que
 * permite CONVERSAR com o Ultron com o PC desligado, e não só executar
 * comandos do aparelho (LocalCommands.kt).
 *
 * A configuração (URL/chave/modelo/prompt de personalidade) vem do PC
 * uma única vez, via GET /ia/config enquanto ele está ligado (ver
 * MainActivity.sincronizarIaConfig), e fica guardada em Prefs. Precisa
 * de INTERNET no celular -- "sem o PC" não é "sem rede nenhuma": o
 * cérebro da conversa continua sendo o provedor de IA remoto.
 *
 * Limitação honesta: por este caminho o Ultron NÃO tem acesso à memória,
 * base de conhecimento nem aos plugins do PC -- é conversa pura com a
 * personalidade dele. Um histórico curto (últimas trocas desta sessão do
 * app) é mantido em memória só pra conversa ter continuidade.
 */
object CloudAI {

    private const val MAX_HISTORICO = 12  // últimas N mensagens (user+assistant)
    private val historico = mutableListOf<Pair<String, String>>()  // role -> texto

    fun conversar(prefs: Prefs, texto: String): String {
        val mensagens = JSONArray()
        val prompt = prefs.iaSystemPrompt
        if (prompt.isNotEmpty()) {
            mensagens.put(JSONObject().put("role", "system").put("content", prompt))
        }
        synchronized(historico) {
            for ((role, conteudo) in historico) {
                mensagens.put(JSONObject().put("role", role).put("content", conteudo))
            }
        }
        mensagens.put(JSONObject().put("role", "user").put("content", texto))

        val corpo = JSONObject()
            .put("model", prefs.iaModelo)
            .put("messages", mensagens)
            .put("max_tokens", 512)

        val conn = URL(prefs.iaBaseUrl.trimEnd('/') + "/chat/completions").openConnection() as HttpURLConnection
        val resposta: String
        try {
            conn.requestMethod = "POST"
            conn.connectTimeout = 10000
            conn.readTimeout = 90000
            conn.doOutput = true
            conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            val header = prefs.iaAuthHeader.ifEmpty { "Authorization" }
            val valor = if (header == "Authorization") "Bearer ${prefs.iaApiKey}" else prefs.iaApiKey
            conn.setRequestProperty(header, valor)
            conn.outputStream.use { it.write(corpo.toString().toByteArray(Charsets.UTF_8)) }

            val status = conn.responseCode
            val stream = if (status in 200..299) conn.inputStream else conn.errorStream
            val textoResposta = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() } ?: "{}"
            if (status !in 200..299) {
                throw Exception("provedor de IA respondeu HTTP $status")
            }
            val json = JSONObject(textoResposta)
            resposta = json.optJSONArray("choices")
                ?.optJSONObject(0)
                ?.optJSONObject("message")
                ?.optString("content", "")
                ?.trim()
                ?: ""
            if (resposta.isEmpty()) throw Exception("resposta vazia do provedor")
        } finally {
            conn.disconnect()
        }

        synchronized(historico) {
            historico.add("user" to texto)
            historico.add("assistant" to resposta)
            while (historico.size > MAX_HISTORICO) historico.removeAt(0)
        }
        return resposta
    }
}
