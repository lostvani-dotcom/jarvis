package com.jarvis.companion

import android.view.LayoutInflater
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Lista de conversas salvas, mostrada no painel deslizante (drawer) da
 * tela principal -- toque abre a conversa, toque longo oferece excluir
 * (ver MainActivity.abrirDrawerComSessoes). */
class SessionsAdapter(
    private val aoTocar: (ChatSession) -> Unit,
    private val aoSegurar: (ChatSession) -> Unit,
) : RecyclerView.Adapter<SessionsAdapter.ViewHolder>() {

    private var sessoes: List<ChatSession> = emptyList()
    private val formatoData = SimpleDateFormat("dd/MM HH:mm", Locale("pt", "BR"))

    class ViewHolder(view: android.view.View) : RecyclerView.ViewHolder(view) {
        val titulo: TextView = view.findViewById(R.id.sessionTitle)
        val subtitulo: TextView = view.findViewById(R.id.sessionSubtitle)
    }

    fun atualizar(novaLista: List<ChatSession>) {
        sessoes = novaLista
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val view = LayoutInflater.from(parent.context).inflate(R.layout.item_session, parent, false)
        return ViewHolder(view)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        val sessao = sessoes[position]
        holder.titulo.text = sessao.titulo.ifBlank { "Conversa" }
        val qtdMensagens = sessao.mensagens.count { it.remetente == Remetente.USUARIO || it.remetente == Remetente.ULTRON }
        holder.subtitulo.text = "${formatoData.format(Date(sessao.atualizadoEm))} · $qtdMensagens mensagens"
        holder.itemView.setOnClickListener { aoTocar(sessao) }
        holder.itemView.setOnLongClickListener {
            aoSegurar(sessao)
            true
        }
    }

    override fun getItemCount(): Int = sessoes.size
}
