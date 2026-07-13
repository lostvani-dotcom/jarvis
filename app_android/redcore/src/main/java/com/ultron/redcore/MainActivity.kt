package com.ultron.redcore

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Bitmap
import android.os.Bundle
import android.text.TextUtils
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.ultron.redcore.databinding.ActivityMainBinding
import java.net.URLEncoder

private const val PAGINA_INICIAL = "https://www.google.com/"
private const val LARGURA_MAX_TITULO = 18

/**
 * RedCore Mobile: versão leve do navegador do Ultron (gui/redcore.py,
 * no PC) pro celular -- abas, barra de endereço com busca embutida,
 * voltar/avançar/recarregar, mesmo visual (fundo quase preto, acento
 * vermelho). NÃO tenta portar cada recurso do desktop (favoritos,
 * downloads, bloqueio de anúncios e aba privada continuam exclusivos
 * do RedCore do PC por enquanto) -- é o essencial de um navegador de
 * verdade, no bolso.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private val abas = mutableListOf<Aba>()
    private var abaAtivaIndex = -1

    private class Aba(val webView: WebView, val chip: LinearLayout, val tituloView: TextView)

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.backButton.setOnClickListener {
            abaAtual()?.webView?.let { wv -> if (wv.canGoBack()) wv.goBack() }
        }
        binding.forwardButton.setOnClickListener {
            abaAtual()?.webView?.let { wv -> if (wv.canGoForward()) wv.goForward() }
        }
        binding.reloadButton.setOnClickListener { abaAtual()?.webView?.reload() }
        binding.newTabButton.setOnClickListener { novaAba(PAGINA_INICIAL) }

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
}
