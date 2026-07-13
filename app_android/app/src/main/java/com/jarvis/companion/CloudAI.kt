package com.jarvis.companion

import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * Conversa DIRETO com o provedor de IA (formato OpenAI chat/completions,
 * mesmo protocolo de ia/providers/openai_compatible.py do PC) -- é o que
 * permite CONVERSAR com o Ultron com o PC desligado, e não só executar
 * comandos do aparelho (LocalCommands.kt). É o "modo nuvem": funciona de
 * qualquer lugar, só precisa de internet no celular.
 *
 * A configuração (URL/chave/modelo/prompt de personalidade) vem do PC
 * via GET /ia/config sempre que o celular consegue alcançá-lo (ver
 * MainActivity.sincronizarIaConfig e NotifyListenerService, que
 * re-sincroniza sozinho em segundo plano) e fica guardada em Prefs.
 *
 * Histórico PERSISTENTE (Prefs.iaHistoricoJson) -- sobrevive fechar e
 * reabrir o app, diferente de uma versão anterior que guardava só em
 * memória. Isso é o que faz o modo nuvem parecer uma conversa contínua
 * de verdade, não uma sessão que reseta toda vez que o app é fechado.
 *
 * Limitação honesta: por este caminho o Ultron NÃO tem acesso à memória,
 * base de conhecimento nem aos plugins do PC -- é conversa pura com a
 * personalidade dele, só as últimas trocas guardadas aqui pra dar
 * continuidade.
 */
object CloudAI {

    private const val MAX_HISTORICO = 12  // últimas N mensagens (user+assistant)

    private fun carregarHistorico(prefs: Prefs): MutableList<Pair<String, String>> {
        val lista = mutableListOf<Pair<String, String>>()
        try {
            val array = JSONArray(prefs.iaHistoricoJson)
            for (i in 0 until array.length()) {
                val item = array.getJSONObject(i)
                lista.add(item.getString("role") to item.getString("content"))
            }
        } catch (e: Exception) {
            // histórico corrompido/vazio -- começa do zero, sem travar a conversa
        }
        return lista
    }

    private fun salvarHistorico(prefs: Prefs, historico: List<Pair<String, String>>) {
        val array = JSONArray()
        for ((role, conteudo) in historico) {
            array.put(JSONObject().put("role", role).put("content", conteudo))
        }
        prefs.iaHistoricoJson = array.toString()
    }

    fun limparHistorico(prefs: Prefs) {
        prefs.iaHistoricoJson = "[]"
    }

    fun conversar(prefs: Prefs, texto: String): String {
        val historico = carregarHistorico(prefs)

        val mensagens = JSONArray()
        val prompt = prefs.iaSystemPrompt
        if (prompt.isNotEmpty()) {
            mensagens.put(JSONObject().put("role", "system").put("content", prompt))
        }
        for ((role, conteudo) in historico) {
            mensagens.put(JSONObject().put("role", role).put("content", conteudo))
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

        historico.add("user" to texto)
        historico.add("assistant" to resposta)
        while (historico.size > MAX_HISTORICO) historico.removeAt(0)
        salvarHistorico(prefs, historico)

        return resposta
    }
}
