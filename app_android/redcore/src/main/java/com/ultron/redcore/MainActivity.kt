package com.ultron.redcore

import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.text.TextUtils
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import com.ultron.redcore.databinding.ActivityMainBinding
import java.io.File
import java.net.URLEncoder
import kotlin.concurrent.thread

private const val PAGINA_INICIAL = "redcore://home"  // sentinela -- ver novaAba() e gerarHtmlNovaAba()
private const val LARGURA_MAX_TITULO = 18

/** Mesmo "usuário padrão" usado em todo o resto do projeto quando não
 * há login/multi-perfil de verdade (ver server/http_server.py e os
 * outros módulos do pacote automacao) -- favoritos e histórico do
 * celular caem no mesmo balde do RedCore do PC. */
private const val USER_ID_PADRAO = "default_user"

/**
 * RedCore Mobile: versão leve do navegador do Ultron (gui/redcore.py,
 * no PC) pro celular -- abas, barra de endereço com busca embutida,
 * voltar/avançar/recarregar, bloqueio de anúncios/rastreadores com
 * painel Shields estilo Brave (ver mostrarShields), modo leitura (ver
 * ReaderMode.kt), nova aba com busca + grade de favoritos estilo
 * speed dial (ver gerarHtmlNovaAba), favoritos sincronizados com o PC
 * nos dois sentidos e sincronização opcional de histórico (ver
 * Prefs.kt/RedCoreClient.kt/AdBlock.kt), mesmo visual (fundo quase
 * preto, acento vermelho). Aba privada continua exclusiva do RedCore
 * do PC por enquanto.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var prefs: Prefs
    private val abas = mutableListOf<Aba>()
    private var abaAtivaIndex = -1

    private class Aba(val webView: WebView, val chip: LinearLayout, val tituloView: TextView) {
        var modoLeitura: Boolean = false
        var bloqueiosPagina: Int = 0
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = Prefs(this)

        binding.backButton.setOnClickListener {
            abaAtual()?.webView?.let { wv -> if (wv.canGoBack()) wv.goBack() }
        }
        binding.forwardButton.setOnClickListener {
            abaAtual()?.webView?.let { wv -> if (wv.canGoForward()) wv.goForward() }
        }
        binding.reloadButton.setOnClickListener { abaAtual()?.webView?.reload() }
        binding.newTabButton.setOnClickListener { novaAba(PAGINA_INICIAL) }
        binding.optionsButton.setOnClickListener { abrirMenuDeOpcoes() }

        binding.addressBar.setOnEditorActionListener { _, actionId, event ->
            val enterPressionado = event?.keyCode == KeyEvent.KEYCODE_ENTER
            if (actionId == EditorInfo.IME_ACTION_GO || enterPressionado) {
                navegarDaBarra()
                true
            } else {
                false
            }
        }

        novaAba(PAGINA_INICIAL)

        if (prefs.host.isNotEmpty()) {
            checarAutoAtualizacao()
        } else {
            thread {
                val resultado = Discovery.buscar()
                if (resultado != null) {
                    prefs.host = resultado.ip
                    prefs.port = resultado.porta.toString()
                    prefs.token = resultado.token
                    checarAutoAtualizacao()
                }
            }
        }
    }

    override fun onDestroy() {
        abas.forEach { it.webView.destroy() }
        super.onDestroy()
    }

    @Suppress("DEPRECATION")
    override fun onBackPressed() {
        val webView = abaAtual()?.webView
        if (webView != null && webView.canGoBack()) {
            webView.goBack()
        } else {
            super.onBackPressed()
        }
    }

    private fun abaAtual(): Aba? = abas.getOrNull(abaAtivaIndex)

    private fun dp(valor: Int): Int = (valor * resources.displayMetrics.density).toInt()

    @SuppressLint("SetJavaScriptEnabled")
    private fun novaAba(url: String) {
        val webView = WebView(this).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.setSupportZoom(true)
            settings.builtInZoomControls = true
            settings.displayZoomControls = false

            webViewClient = object : WebViewClient() {
                override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
                    val indice = indiceDoWebView(view)
                    // Navegação nova sempre desliga o modo leitura e zera a
                    // contagem de bloqueios desta aba -- Shields mostra o
                    // bloqueado NESTA página (mesmo espírito do RedCore do
                    // PC, ver gui/redcore.py).
                    abas.getOrNull(indice)?.let {
                        it.modoLeitura = false
                        it.bloqueiosPagina = 0
                    }
                    if (indice == abaAtivaIndex) {
                        // Nova aba (speed dial) mostra a barra em branco,
                        // mesmo espírito do RedCore do PC (gui/redcore.py)
                        // -- "redcore://home" não é um endereço de verdade.
                        binding.addressBar.setText(if (url == PAGINA_INICIAL) "" else (url ?: ""))
                    }
                }

                override fun onPageFinished(view: WebView?, url: String?) {
                    if (!url.isNullOrBlank()) {
                        sincronizarHistoricoSeAtivo(url, view?.title ?: "")
                    }
                }

                override fun shouldInterceptRequest(
                    view: WebView?, request: android.webkit.WebResourceRequest?,
                ): android.webkit.WebResourceResponse? {
                    val alvo = request?.url?.toString()
                    if (prefs.bloqueioAnuncios && alvo != null && AdBlock.bloqueado(alvo)) {
                        // shouldInterceptRequest pode rodar numa thread de
                        // fundo, e mais de uma chamada pode chegar em
                        // paralelo (várias requisições bloqueadas de uma vez
                        // na mesma página) -- incrementarBloqueiosTotais() é
                        // sincronizado (ver Prefs.kt) pra não perder
                        // contagem num read-modify-write concorrente. E
                        // indiceDoWebView() (que percorre `abas`, mutado só
                        // na UI thread por novaAba()/fecharAba()) só pode
                        // rodar DENTRO do runOnUiThread -- chamá-lo aqui fora
                        // correria com abas.add()/removeAt() e podia lançar
                        // ConcurrentModificationException.
                        prefs.incrementarBloqueiosTotais()
                        runOnUiThread {
                            val indice = indiceDoWebView(view)
                            abas.getOrNull(indice)?.let { it.bloqueiosPagina += 1 }
                        }
                        return AdBlock.respostaVazia()
                    }
                    return super.shouldInterceptRequest(view, request)
                }
            }
            webChromeClient = object : WebChromeClient() {
                override fun onReceivedTitle(view: WebView?, title: String?) {
                    val indice = indiceDoWebView(view)
                    if (indice != -1) atualizarTituloAba(indice, title ?: "Nova aba")
                }
            }
        }

        val chip = criarChipDeAba()
        val aba = Aba(webView, chip, chip.getChildAt(0) as TextView)
        abas.add(aba)
        binding.tabStrip.addView(chip)

        chip.setOnClickListener { selecionarAba(abas.indexOf(aba)) }
        (chip.getChildAt(1) as View).setOnClickListener { fecharAba(abas.indexOf(aba)) }

        selecionarAba(abas.size - 1)
        if (url == PAGINA_INICIAL) {
            // Nova aba (speed dial): renderizada localmente, não pede
            // nada pra rede -- ver gerarHtmlNovaAba(). historyUrl =
            // baseUrl = PAGINA_INICIAL pra webView.url refletir a
            // sentinela (mesmo truque de QWebEngineView.setHtml no PC).
            webView.loadDataWithBaseURL(PAGINA_INICIAL, gerarHtmlNovaAba(), "text/html", "utf-8", PAGINA_INICIAL)
        } else {
            webView.loadUrl(url)
        }
    }

    /** Nova aba estilo Brave/Chrome: caixa de busca + grade de
     * favoritos (Prefs.listarFavoritos, já sincronizados com o PC),
     * mesma paleta vermelho/escuro do resto do app -- "interface do
     * Brave" aqui é o padrão de interação (busca + atalhos em grade),
     * não uma repintura de marca. Mesma lógica de
     * gui/redcore.py:_gerar_html_nova_aba. */
    private fun gerarHtmlNovaAba(): String {
        val favoritos = prefs.listarFavoritos().take(12)
        val tiles = if (favoritos.isEmpty()) {
            "<p class=\"vazio\">Nenhum favorito ainda -- toque em ⋮ numa página pra favoritar.</p>"
        } else {
            favoritos.joinToString("") { f ->
                val url = f.url
                // Só http(s) -- sincronizarFavoritosDoPc() grava direto via
                // salvarFavoritos(), sem passar por alternarFavorito(), então
                // um favorito ruim vindo do PC (ex.: "javascript:...") pode
                // parar aqui mesmo com a validação nos outros pontos. Sem
                // esse filtro, viraria um <a href> clicável executando
                // script na origem do WebView.
                if (!url.startsWith("http://") && !url.startsWith("https://")) return@joinToString ""
                val titulo = f.titulo.ifBlank { url }
                val host = try { Uri.parse(url).host } catch (e: Exception) { null }
                val inicial = (host?.firstOrNull() ?: titulo.firstOrNull() ?: '?').uppercaseChar()
                val urlEscapada = android.text.Html.escapeHtml(url)
                val tituloEscapado = android.text.Html.escapeHtml(titulo.take(22))
                val inicialEscapada = android.text.Html.escapeHtml(inicial.toString())
                """
                <a class="tile" href="$urlEscapada">
                  <div class="tile-icone">$inicialEscapada</div>
                  <div class="tile-titulo">$tituloEscapado</div>
                </a>"""
            }
        }
        return """
        <!DOCTYPE html>
        <html lang="pt-br">
        <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Nova aba</title>
        <style>
          * { box-sizing: border-box; }
          body {
            margin: 0; min-height: 100vh; display: flex; flex-direction: column;
            align-items: center; justify-content: center; gap: 26px; padding: 24px 16px;
            background: #0c0505; color: #fbf9f9; font-family: sans-serif;
          }
          form { width: 100%; max-width: 420px; }
          input[type="text"] {
            width: 100%; padding: 12px 16px; font-size: 15px; border-radius: 22px;
            border: 1px solid #382323; background: #1b1010; color: #fbf9f9; outline: none;
          }
          .grade {
            display: grid; grid-template-columns: repeat(auto-fit, 80px); gap: 14px;
            justify-content: center; width: 100%; max-width: 420px;
          }
          .tile {
            display: flex; flex-direction: column; align-items: center; gap: 6px;
            text-decoration: none; color: #e7e5e5; padding: 8px 2px; border-radius: 10px;
          }
          .tile-icone {
            width: 40px; height: 40px; border-radius: 50%; background: #241515;
            border: 1px solid #382323; display: flex; align-items: center; justify-content: center;
            font-size: 15px; font-weight: 600; color: #ff5f52;
          }
          .tile-titulo {
            font-size: 11px; text-align: center; max-width: 78px; overflow: hidden;
            text-overflow: ellipsis; white-space: nowrap; color: #c9baba;
          }
          .vazio { color: #8f7c7c; font-size: 12px; max-width: 280px; text-align: center; }
          .marca { color: #c9baba; font-size: 18px; font-weight: 600; }
        </style>
        </head>
        <body>
          <div class="marca">🔴 RedCore</div>
          <form action="https://www.google.com/search" method="GET">
            <input type="text" name="q" placeholder="Pesquisar ou digitar um endereço" autofocus>
          </form>
          <div class="grade">$tiles</div>
        </body>
        </html>
        """.trimIndent()
    }

    private fun indiceDoWebView(view: WebView?): Int = abas.indexOfFirst { it.webView === view }

    private fun criarChipDeAba(): LinearLayout {
        val chip = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(12), dp(8), dp(8), dp(8))
            background = ContextCompat.getDrawable(this@MainActivity, R.drawable.bg_tab_inativa)
            layoutParams = LinearLayout.LayoutParams(dp(140), LinearLayout.LayoutParams.WRAP_CONTENT).apply {
                marginEnd = dp(4)
            }
        }
        val titulo = TextView(this).apply {
            text = "Nova aba"
            setTextColor(0xFFC9BABA.toInt())
            textSize = 12f
            maxLines = 1
            ellipsize = TextUtils.TruncateAt.END
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        }
        val fechar = TextView(this).apply {
            text = "✕"
            setTextColor(0xFF8F7C7C.toInt())
            textSize = 12f
            setPadding(dp(8), 0, 0, 0)
        }
        chip.addView(titulo)
        chip.addView(fechar)
        return chip
    }

    private fun selecionarAba(index: Int) {
        if (index !in abas.indices) return
        abaAtivaIndex = index
        binding.webViewContainer.removeAllViews()
        binding.webViewContainer.addView(abas[index].webView)
        binding.addressBar.setText(abas[index].webView.url ?: "")
        atualizarEstiloChips()
    }

    private fun atualizarEstiloChips() {
        abas.forEachIndexed { i, aba ->
            aba.chip.background = ContextCompat.getDrawable(
                this, if (i == abaAtivaIndex) R.drawable.bg_tab_ativa else R.drawable.bg_tab_inativa,
            )
            aba.tituloView.setTextColor(if (i == abaAtivaIndex) 0xFFFF5F52.toInt() else 0xFFC9BABA.toInt())
        }
    }

    private fun atualizarTituloAba(index: Int, titulo: String) {
        val curto = if (titulo.length > LARGURA_MAX_TITULO) titulo.take(LARGURA_MAX_TITULO) + "…" else titulo.ifBlank { "Nova aba" }
        abas.getOrNull(index)?.tituloView?.text = curto
    }

    private fun fecharAba(index: Int) {
        if (index !in abas.indices) return
        val aba = abas[index]
        binding.tabStrip.removeView(aba.chip)
        aba.webView.destroy()
        abas.removeAt(index)
        if (abas.isEmpty()) {
            finish()
            return
        }
        val novoIndex = (index - 1).coerceAtLeast(0).coerceAtMost(abas.size - 1)
        selecionarAba(novoIndex)
    }

    private fun navegarDaBarra() {
        val texto = binding.addressBar.text.toString().trim()
        if (texto.isEmpty()) return
        abaAtual()?.webView?.loadUrl(resolverEndereco(texto))
        val imm = getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        imm.hideSoftInputFromWindow(binding.addressBar.windowToken, 0)
    }

    /** Mesma lógica de gui/redcore.py:_resolver_endereco -- URL direta
     * se parecer com uma, senão pesquisa no Google. */
    private fun resolverEndereco(texto: String): String {
        if (texto.startsWith("http://") || texto.startsWith("https://")) return texto
        if (texto.contains(".") && !texto.contains(" ")) return "https://$texto"
        return "https://www.google.com/search?q=" + URLEncoder.encode(texto, "UTF-8")
    }

    // ---- Menu de opções (favoritos + configurações) ----

    private fun abrirMenuDeOpcoes() {
        val urlAtual = abaAtual()?.webView?.url ?: ""
        val jaFavorito = urlAtual.isNotEmpty() && prefs.ehFavorito(urlAtual)
        val bloqueiosPagina = abaAtual()?.bloqueiosPagina ?: 0
        val opcoes = arrayOf(
            if (jaFavorito) "☆ Remover dos favoritos" else "⭐ Favoritar esta página",
            "Meus favoritos",
            "🛡 Shields ($bloqueiosPagina bloqueado(s) nesta página)",
            if (abaAtual()?.modoLeitura == true) "📖 Modo leitura: ligado" else "📖 Modo leitura",
            "Configurações",
        )
        AlertDialog.Builder(this)
            .setItems(opcoes) { _, which ->
                when (which) {
                    0 -> alternarFavoritoAtual()
                    1 -> mostrarFavoritos()
                    2 -> mostrarShields()
                    3 -> alternarModoLeitura()
                    4 -> mostrarConfiguracoes()
                }
            }
            .show()
    }

    /** Painel "Shields", estilo Brave: quanto foi bloqueado NESTA
     * página, o total desde sempre, e o interruptor de ligar/desligar
     * -- tudo num lugar só, com contexto pra decisão, em vez de um
     * toggle solto sem número nenhum do que ele está fazendo. */
    private fun mostrarShields() {
        val aba = abaAtual()
        val host = aba?.webView?.url?.let { android.net.Uri.parse(it).host } ?: ""
        val bloqueiosPagina = aba?.bloqueiosPagina ?: 0

        val view = layoutInflater.inflate(R.layout.dialog_shields, null)
        view.findViewById<TextView>(R.id.shieldsTitulo).text =
            if (host.isNullOrEmpty()) "🛡 Shields" else "🛡 Shields para $host"
        view.findViewById<TextView>(R.id.shieldsPagina).text =
            "$bloqueiosPagina rastreador(es)/anúncio(s) bloqueado(s) nesta página."
        view.findViewById<TextView>(R.id.shieldsTotal).text =
            "${prefs.bloqueiosTotais} bloqueado(s) ao todo, desde sempre."
        val chk = view.findViewById<CheckBox>(R.id.shieldsToggle)
        chk.isChecked = prefs.bloqueioAnuncios

        AlertDialog.Builder(this)
            .setView(view)
            .setPositiveButton("Fechar") { _, _ ->
                if (chk.isChecked != prefs.bloqueioAnuncios) {
                    prefs.bloqueioAnuncios = chk.isChecked
                    Toast.makeText(
                        this,
                        if (prefs.bloqueioAnuncios) "Bloqueio de anúncios ligado." else "Bloqueio de anúncios desligado.",
                        Toast.LENGTH_SHORT,
                    ).show()
                    abaAtual()?.webView?.reload()
                }
            }
            .show()
    }

    /** Limpa o clutter da página (heurística, ver ReaderMode.kt) -- por
     * aba, some sozinho na próxima navegação (ver onPageStarted). O
     * próprio JS já alterna sozinho (remove o &lt;style&gt; se já
     * existir), então só refletimos o retorno real no estado da aba. */
    private fun alternarModoLeitura() {
        val aba = abaAtual() ?: return
        aba.webView.evaluateJavascript(ReaderMode.JS) { retorno ->
            aba.modoLeitura = retorno == "true"
        }
    }

    private fun alternarFavoritoAtual() {
        val webView = abaAtual()?.webView ?: return
        val url = webView.url ?: return
        if (url == PAGINA_INICIAL) return  // nova aba (speed dial) não é favoritável
        val titulo = webView.title ?: url
        val agoraFavorito = prefs.alternarFavorito(titulo, url)
        Toast.makeText(
            this,
            if (agoraFavorito) "Adicionado aos favoritos." else "Removido dos favoritos.",
            Toast.LENGTH_SHORT,
        ).show()
        // Sincroniza com o PC em segundo plano, sem bloquear a UI --
        // favoritar é deliberado (diferente de histórico), então não é
        // opt-in: sincroniza sempre que o PC estiver configurado.
        if (prefs.host.isNotEmpty()) {
            thread {
                try {
                    val acao = if (agoraFavorito) "adicionar" else "remover"
                    RedCoreClient.sincronizarFavoritoPC(prefs.baseUrl, prefs.token, USER_ID_PADRAO, url, titulo, acao)
                } catch (e: Exception) {
                    // melhor-esforço -- PC fora de alcance agora, o favorito
                    // continua salvo localmente, só não propagou desta vez.
                }
            }
        }
    }

    /** Lista os favoritos com checkbox (marcado = mantém, desmarcado =
     * remove ao confirmar) -- toque no texto do item navega direto pra
     * ele, mesmo diálogo servindo pra "abrir" e "gerenciar" sem
     * precisar de uma tela/RecyclerView dedicada só pra isso. Mostra
     * os favoritos LOCAIS na hora (sem esperar rede) -- a sincronização
     * com o PC roda em paralelo e só avisa se trouxe algo novo, pra
     * abrir o menu de novo pegar a lista já mesclada. */
    private fun mostrarFavoritos() {
        val favoritos = prefs.listarFavoritos()
        sincronizarFavoritosDoPc()
        if (favoritos.isEmpty()) {
            Toast.makeText(this, "Nenhum favorito ainda -- toque em ⋮ numa página pra favoritar.", Toast.LENGTH_LONG).show()
            return
        }
        val titulos = favoritos.map { it.titulo }.toTypedArray()
        AlertDialog.Builder(this)
            .setTitle("Favoritos (toque pra abrir)")
            .setItems(titulos) { _, which ->
                val url = favoritos[which].url
                // Defesa em profundidade -- ver gerarHtmlNovaAba: não abre
                // um favorito com esquema fora de http(s).
                if (url.startsWith("http://") || url.startsWith("https://")) {
                    novaAba(url)
                } else {
                    Toast.makeText(this, "Favorito com endereço inválido -- remova-o.", Toast.LENGTH_SHORT).show()
                }
            }
            .setNegativeButton("Gerenciar") { _, _ -> gerenciarFavoritos(favoritos) }
            .setPositiveButton("Fechar", null)
            .show()
    }

    /** Puxa os favoritos salvos no RedCore do PC e mescla com os
     * locais (só adiciona URLs que ainda não existem aqui -- nunca
     * remove um favorito local só porque o PC não tem ele, pra não
     * apagar por engano algo que só existia neste celular). */
    private fun sincronizarFavoritosDoPc() {
        if (prefs.host.isEmpty()) return
        thread {
            try {
                val doPc = RedCoreClient.listarFavoritosPC(prefs.baseUrl, prefs.token, USER_ID_PADRAO)
                val locaisUrls = prefs.listarFavoritos().map { it.url }.toSet()
                val novos = doPc.filter { it.url !in locaisUrls }
                if (novos.isNotEmpty()) {
                    val combinados = prefs.listarFavoritos() + novos
                    prefs.salvarFavoritos(combinados)
                    runOnUiThread {
                        Toast.makeText(this, "${novos.size} favorito(s) sincronizado(s) do PC.", Toast.LENGTH_SHORT).show()
                    }
                }
            } catch (e: Exception) {
                // melhor-esforço -- PC fora de alcance, segue só com os locais
            }
        }
    }

    private fun gerenciarFavoritos(favoritos: List<Favorito>) {
        val titulos = favoritos.map { it.titulo }.toTypedArray()
        val marcados = BooleanArray(favoritos.size) { true }
        AlertDialog.Builder(this)
            .setTitle("Desmarque pra remover")
            .setMultiChoiceItems(titulos, marcados) { _, indice, marcado -> marcados[indice] = marcado }
            .setPositiveButton("Salvar") { _, _ ->
                val remover = favoritos.filterIndexed { i, _ -> !marcados[i] }.map { it.url }.toSet()
                if (remover.isNotEmpty()) {
                    prefs.removerFavoritos(remover)
                    Toast.makeText(this, "${remover.size} favorito(s) removido(s).", Toast.LENGTH_SHORT).show()
                }
            }
            .setNegativeButton("Cancelar", null)
            .show()
    }

    private fun mostrarConfiguracoes() {
        val view = layoutInflater.inflate(R.layout.dialog_config, null)
        val hostInput = view.findViewById<EditText>(R.id.dialogHostInput)
        val portInput = view.findViewById<EditText>(R.id.dialogPortInput)
        val tokenInput = view.findViewById<EditText>(R.id.dialogTokenInput)
        val syncCheck = view.findViewById<CheckBox>(R.id.dialogSyncHistoryCheck)
        val discoverButton = view.findViewById<android.widget.Button>(R.id.dialogDiscoverButton)

        hostInput.setText(prefs.host)
        portInput.setText(prefs.port)
        tokenInput.setText(prefs.token)
        syncCheck.isChecked = prefs.sincronizarHistorico

        discoverButton.setOnClickListener {
            discoverButton.isEnabled = false
            discoverButton.text = "Procurando..."
            thread {
                val resultado = Discovery.buscar()
                runOnUiThread {
                    discoverButton.isEnabled = true
                    discoverButton.text = "Buscar o Ultron automaticamente"
                    if (resultado != null) {
                        hostInput.setText(resultado.ip)
                        portInput.setText(resultado.porta.toString())
                        tokenInput.setText(resultado.token)
                    } else {
                        Toast.makeText(this, "Não encontrei o Ultron na rede.", Toast.LENGTH_SHORT).show()
                    }
                }
            }
        }

        AlertDialog.Builder(this)
            .setTitle("Conexão com o Ultron do PC")
            .setView(view)
            .setPositiveButton("Salvar") { _, _ ->
                prefs.host = hostInput.text.toString().trim()
                prefs.port = portInput.text.toString().trim().ifEmpty { "8765" }
                prefs.token = tokenInput.text.toString().trim()
                prefs.sincronizarHistorico = syncCheck.isChecked
                Toast.makeText(this, "Configuração salva.", Toast.LENGTH_SHORT).show()
                if (prefs.host.isNotEmpty()) checarAutoAtualizacao()
            }
            .setNegativeButton("Cancelar", null)
            .show()
    }

    // ---- Sincronização de histórico com o PC (opt-in, ver Prefs.sincronizarHistorico) ----

    private fun sincronizarHistoricoSeAtivo(url: String, titulo: String) {
        if (!prefs.sincronizarHistorico || prefs.host.isEmpty()) return
        // Só http(s) de verdade -- ignora about:blank, data:, file: etc.
        if (!url.startsWith("http://") && !url.startsWith("https://")) return
        thread {
            try {
                RedCoreClient.enviarHistorico(prefs.baseUrl, prefs.token, url, titulo)
            } catch (e: Exception) {
                // melhor-esforço -- não incomoda o usuário se o PC estiver
                // fora de alcance no momento, só não sincroniza essa visita.
            }
        }
    }

    // ---- Autoatualização (mesmo catálogo da Loja, ver server/loja_catalogo.py) ----

    private fun checarAutoAtualizacao() {
        thread {
            try {
                val apps = RedCoreClient.catalogo(prefs.baseUrl)
                val entrada = apps.firstOrNull { it.id == "redcore-mobile" && it.disponivel } ?: return@thread
                val versaoAtual = packageManager.getPackageInfo(packageName, 0).let {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) it.longVersionCode.toInt() else @Suppress("DEPRECATION") it.versionCode
                }
                if (entrada.versaoCodigo <= versaoAtual) return@thread
                runOnUiThread {
                    Toast.makeText(this, "Atualizando o RedCore pra versão ${entrada.versaoNome}...", Toast.LENGTH_SHORT).show()
                }
                val destino = File(cacheDir, entrada.arquivo)
                RedCoreClient.baixarApk(prefs.baseUrl, entrada.arquivo, destino)
                runOnUiThread { dispararInstalacao(destino) }
            } catch (e: Exception) {
                // melhor-esforço -- sem PC alcançável, sem checagem de versão
            }
        }
    }

    private fun dispararInstalacao(arquivo: File) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && !packageManager.canRequestPackageInstalls()) {
            Toast.makeText(
                this, "Autorize \"Instalar apps desconhecidos\" pro RedCore, e reabra o app pra atualizar.",
                Toast.LENGTH_LONG,
            ).show()
            try {
                startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:$packageName")))
            } catch (e: Exception) {
                // melhor-esforço -- o ACTION_VIEW abaixo ainda tenta
            }
        }
        val uri = FileProvider.getUriForFile(this, "$packageName.fileprovider", arquivo)
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        startActivity(intent)
    }
}
