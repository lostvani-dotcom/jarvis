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

private const val PAGINA_INICIAL = "https://www.google.com/"
private const val LARGURA_MAX_TITULO = 18

/**
 * RedCore Mobile: versão leve do navegador do Ultron (gui/redcore.py,
 * no PC) pro celular -- abas, barra de endereço com busca embutida,
 * voltar/avançar/recarregar, favoritos e sincronização opcional de
 * histórico com o PC (ver Prefs.kt/RedCoreClient.kt), mesmo visual
 * (fundo quase preto, acento vermelho). Bloqueio de anúncios e aba
 * privada continuam exclusivos do RedCore do PC por enquanto.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var prefs: Prefs
    private val abas = mutableListOf<Aba>()
    private var abaAtivaIndex = -1

    private class Aba(val webView: WebView, val chip: LinearLayout, val tituloView: TextView)

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
                    if (indiceDoWebView(view) == abaAtivaIndex) {
                        binding.addressBar.setText(url ?: "")
                    }
                }

                override fun onPageFinished(view: WebView?, url: String?) {
                    if (!url.isNullOrBlank()) {
                        sincronizarHistoricoSeAtivo(url, view?.title ?: "")
                    }
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
        webView.loadUrl(url)
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
        val opcoes = arrayOf(
            if (jaFavorito) "☆ Remover dos favoritos" else "⭐ Favoritar esta página",
            "Meus favoritos",
            "Configurações",
        )
        AlertDialog.Builder(this)
            .setItems(opcoes) { _, which ->
                when (which) {
                    0 -> alternarFavoritoAtual()
                    1 -> mostrarFavoritos()
                    2 -> mostrarConfiguracoes()
                }
            }
            .show()
    }

    private fun alternarFavoritoAtual() {
        val webView = abaAtual()?.webView ?: return
        val url = webView.url ?: return
        val agoraFavorito = prefs.alternarFavorito(webView.title ?: url, url)
        Toast.makeText(
            this,
            if (agoraFavorito) "Adicionado aos favoritos." else "Removido dos favoritos.",
            Toast.LENGTH_SHORT,
        ).show()
    }

    /** Lista os favoritos com checkbox (marcado = mantém, desmarcado =
     * remove ao confirmar) -- toque no texto do item navega direto pra
     * ele, mesmo diálogo servindo pra "abrir" e "gerenciar" sem
     * precisar de uma tela/RecyclerView dedicada só pra isso. */
    private fun mostrarFavoritos() {
        val favoritos = prefs.listarFavoritos()
        if (favoritos.isEmpty()) {
            Toast.makeText(this, "Nenhum favorito ainda -- toque em ⋮ numa página pra favoritar.", Toast.LENGTH_LONG).show()
            return
        }
        val titulos = favoritos.map { it.titulo }.toTypedArray()
        AlertDialog.Builder(this)
            .setTitle("Favoritos (toque pra abrir)")
            .setItems(titulos) { _, which ->
                novaAba(favoritos[which].url)
            }
            .setNegativeButton("Gerenciar") { _, _ -> gerenciarFavoritos(favoritos) }
            .setPositiveButton("Fechar", null)
            .show()
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
