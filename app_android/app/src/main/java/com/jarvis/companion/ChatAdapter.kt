package com.jarvis.companion

import android.text.Html
import android.text.TextUtils
import android.view.LayoutInflater
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView

/** Quem "disse" a mensagem -- decide o layout (bolha à direita, texto
 * plano à esquerda, ou legenda central) e a cor. ERRO reaproveita o
 * mesmo layout de SISTEMA (legenda central), só com cor diferente --
 * ver ChatAdapter.onBindViewHolder(). */
enum class Remetente { USUARIO, ULTRON, SISTEMA, ERRO }

data class ChatMessage(val texto: String, val remetente: Remetente)

/** Lista de mensagens do chat, uma bolha por item -- substitui o
 * antigo TextView único onde tudo era concatenado (ver histórico do
 * app: `adicionarLinha` acumulava tudo numa string HTML só). Visual
 * inspirado no ChatGPT: usuário em bolha colorida à direita, Ultron em
 * texto plano à esquerda (sem bolha), avisos do sistema centralizados
 * e discretos. */
class ChatAdapter : RecyclerView.Adapter<ChatAdapter.ViewHolder>() {

    private val mensagens = mutableListOf<ChatMessage>()

    companion object {
        private const val TIPO_USUARIO = 0
        private const val TIPO_ULTRON = 1
        private const val TIPO_LEGENDA = 2
    }

    class ViewHolder(val textView: TextView) : RecyclerView.ViewHolder(textView)

    override fun getItemViewType(position: Int): Int = when (mensagens[position].remetente) {
        Remetente.USUARIO -> TIPO_USUARIO
        Remetente.ULTRON -> TIPO_ULTRON
        Remetente.SISTEMA, Remetente.ERRO -> TIPO_LEGENDA
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val layoutRes = when (viewType) {
            TIPO_USUARIO -> R.layout.item_message_user
            TIPO_ULTRON -> R.layout.item_message_assistant
            else -> R.layout.item_message_legenda
        }
        val view = LayoutInflater.from(parent.context).inflate(layoutRes, parent, false)
        return ViewHolder(view.findViewById(R.id.messageText))
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        val msg = mensagens[position]
        // "\n" -> "<br>" DEPOIS de escapar o HTML -- sem isso, uma
        // resposta multi-linha (lista de vídeos, linha do tempo etc.)
        // vira uma linha só ilegível dentro do Html.fromHtml (mesma
        // lógica que já existia na versão anterior do app).
        val textoEscapado = TextUtils.htmlEncode(msg.texto).replace("\n", "<br>")
        holder.textView.text = Html.fromHtml(textoEscapado, Html.FROM_HTML_MODE_LEGACY)
        if (msg.remetente == Remetente.ERRO) {
            holder.textView.setTextColor(0xFFF87171.toInt())
        }
    }

    override fun getItemCount(): Int = mensagens.size

    /** Adiciona uma mensagem e retorna a posição dela na lista (útil
     * pra quem chama rolar o RecyclerView até ela). */
    fun adicionar(texto: String, remetente: Remetente): Int {
        mensagens.add(ChatMessage(texto, remetente))
        val posicao = mensagens.size - 1
        notifyItemInserted(posicao)
        return posicao
    }

    /** Snapshot de todas as mensagens da tela agora -- usado pra
     * autosalvar a sessão atual (ver Sessions.kt/MainActivity). */
    fun todasAsMensagens(): List<ChatMessage> = mensagens.toList()

    /** Troca todo o conteúdo da tela por outra conversa (ao abrir uma
     * sessão salva no painel deslizante) ou esvazia (nova conversa). */
    fun substituirTudo(novasMensagens: List<ChatMessage>) {
        mensagens.clear()
        mensagens.addAll(novasMensagens)
        notifyDataSetChanged()
    }
}
