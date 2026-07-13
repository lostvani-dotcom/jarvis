package com.jarvis.companion

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/** Uma conversa salva localmente no celular -- sidebar estilo ChatGPT
 * (ver MainActivity/activity_main.xml, painel do DrawerLayout). Isso é
 * só "qual transcript está sendo mostrado na tela agora": a memória de
 * verdade do Ultron (banco de dados no PC) continua contínua e não
 * depende de qual sessão local está aberta -- trocar de sessão aqui
 * não apaga nem reseta nada do lado do PC. */
data class ChatSession(
    val id: String,
    var titulo: String,
    var atualizadoEm: Long,
    val mensagens: MutableList<ChatMessage>,
)

/** Guarda a lista de sessões como um único JSON em SharedPreferences --
 * simples o bastante pro volume de dados envolvido (texto de conversa,
 * não mídia) e evita puxar dependência de banco de dados só pra isso. */
object Sessions {
    private const val PREFS = "jarvis_sessions"
    private const val CHAVE_LISTA = "lista"
    private const val MAX_SESSOES = 100

    private fun sp(context: Context) = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    private fun remetenteParaStr(r: Remetente): String = r.name
    private fun strParaRemetente(s: String): Remetente = try {
        Remetente.valueOf(s)
    } catch (e: Exception) {
        Remetente.SISTEMA
    }

    private fun sessaoParaJson(s: ChatSession): JSONObject {
        val mensagensJson = JSONArray()
        for (m in s.mensagens) {
            mensagensJson.put(
                JSONObject()
                    .put("texto", m.texto)
                    .put("remetente", remetenteParaStr(m.remetente)),
            )
        }
        return JSONObject()
            .put("id", s.id)
            .put("titulo", s.titulo)
            .put("atualizadoEm", s.atualizadoEm)
            .put("mensagens", mensagensJson)
    }

    private fun jsonParaSessao(o: JSONObject): ChatSession {
        val mensagensJson = o.optJSONArray("mensagens") ?: JSONArray()
        val mensagens = mutableListOf<ChatMessage>()
        for (i in 0 until mensagensJson.length()) {
            val m = mensagensJson.getJSONObject(i)
            mensagens.add(ChatMessage(m.optString("texto"), strParaRemetente(m.optString("remetente"))))
        }
        return ChatSession(
            id = o.optString("id"),
            titulo = o.optString("titulo"),
            atualizadoEm = o.optLong("atualizadoEm"),
            mensagens = mensagens,
        )
    }

    /** Todas as sessões salvas, mais recente primeiro. */
    fun listar(context: Context): List<ChatSession> {
        val texto = sp(context).getString(CHAVE_LISTA, "[]") ?: "[]"
        val array = try {
            JSONArray(texto)
        } catch (e: Exception) {
            JSONArray()
        }
        val sessoes = mutableListOf<ChatSession>()
        for (i in 0 until array.length()) {
            sessoes.add(jsonParaSessao(array.getJSONObject(i)))
        }
        return sessoes.sortedByDescending { it.atualizadoEm }
    }

    private fun salvarLista(context: Context, sessoes: List<ChatSession>) {
        val array = JSONArray()
        // Limita o total guardado -- sem isso, meses de uso acumulariam
        // um SharedPreferences cada vez mais pesado pra carregar.
        for (s in sessoes.sortedByDescending { it.atualizadoEm }.take(MAX_SESSOES)) {
            array.put(sessaoParaJson(s))
        }
        sp(context).edit().putString(CHAVE_LISTA, array.toString()).apply()
    }

    /** Cria (ou atualiza, se o id já existir) uma sessão com as
     * mensagens atuais da tela. O título é derivado da primeira
     * mensagem do usuário (como o ChatGPT faz), truncado. Ignora
     * sessões vazias ou sem nenhuma mensagem de USUARIO (não vale a
     * pena salvar uma conversa que nunca aconteceu de verdade). */
    fun salvar(context: Context, id: String, mensagens: List<ChatMessage>) {
        val temMensagemDeUsuario = mensagens.any { it.remetente == Remetente.USUARIO }
        if (!temMensagemDeUsuario) return

        val titulo = mensagens.firstOrNull { it.remetente == Remetente.USUARIO }
            ?.texto
            ?.take(48)
            ?: "Conversa"

        val sessoes = listar(context).toMutableList()
        val existente = sessoes.indexOfFirst { it.id == id }
        val sessao = ChatSession(id, titulo, System.currentTimeMillis(), mensagens.toMutableList())
        if (existente >= 0) sessoes[existente] = sessao else sessoes.add(0, sessao)
        salvarLista(context, sessoes)
    }

    fun excluir(context: Context, id: String) {
        val sessoes = listar(context).filterNot { it.id == id }
        salvarLista(context, sessoes)
    }

    fun novoId(): String = "s_${System.currentTimeMillis()}_${(0..9999).random()}"
}
