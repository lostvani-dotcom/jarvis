package com.ultron.loja

import android.content.Intent
import android.graphics.Typeface
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import com.ultron.loja.databinding.ActivityMainBinding
import java.io.File
import java.util.Locale
import kotlin.concurrent.thread

/**
 * Loja Ultron: descobre o Ultron na rede local (mesmo broadcast UDP do
 * app Companion), busca o catálogo (GET /loja/catalogo, ver
 * server/loja_catalogo.py) e instala qualquer app dele com um toque --
 * sem loja de terceiros, tudo direto do seu próprio Ultron.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var prefs: Prefs

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = Prefs(this)

        binding.refreshButton.setOnClickListener { buscarECarregar() }

        if (prefs.host.isNotEmpty()) {
            carregarCatalogo()
        } else {
            buscarECarregar()
        }
    }

    /** Manda o broadcast UDP e, achando o Ultron, já carrega o
     * catálogo em seguida -- mesmo fluxo "sem digitar nada" do app
     * Companion (ver Discovery.kt). */
    private fun buscarECarregar() {
        setStatus("Procurando o Ultron na rede...")
        binding.refreshButton.isEnabled = false
        thread {
            val resultado = Discovery.buscar()
            runOnUiThread { binding.refreshButton.isEnabled = true }
            if (resultado == null) {
                runOnUiThread {
                    setStatus("Não encontrei o Ultron na rede -- confira se ele está rodando, na mesma Wi-Fi.")
                }
                return@thread
            }
            prefs.host = resultado.ip
            prefs.port = resultado.porta.toString()
            runOnUiThread { carregarCatalogo() }
        }
    }

    private fun carregarCatalogo() {
        setStatus("Conectando em ${prefs.host}:${prefs.port}...")
        thread {
            try {
                val apps = StoreClient.catalogo(prefs.baseUrl)
                runOnUiThread {
                    val disponiveis = apps.count { it.disponivel }
                    setStatus("Conectado em ${prefs.host} -- $disponiveis app(s) disponível(is)")
                    montarLista(apps)
                }
            } catch (e: Exception) {
                runOnUiThread {
                    setStatus("Não consegui buscar o catálogo (${e.message}). Toque em \"Buscar\" pra tentar de novo.")
                }
            }
        }
    }

    private fun setStatus(texto: String) {
        binding.statusText.text = texto
    }

    private fun montarLista(apps: List<AppEntry>) {
        binding.appList.removeAllViews()
        if (apps.isEmpty()) {
            binding.appList.addView(textoSimples("Nenhum app publicado ainda."))
            return
        }
        for (app in apps) {
            binding.appList.addView(criarCard(app))
        }
    }

    private fun textoSimples(texto: String): TextView = TextView(this).apply {
        text = texto
        setTextColor(0xFFC9BABA.toInt())
        setPadding(8, dp(24), 8, 8)
    }

    private fun dp(valor: Int): Int = (valor * resources.displayMetrics.density).toInt()

    /** Monta um "cartão" de app inteiramente em código (sem RecyclerView
     * nem layout XML por item -- o catálogo é pequeno, e o resto do
     * projeto já segue esse mesmo estilo simples de views diretas). */
    private fun criarCard(app: AppEntry): View {
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(16), dp(18), dp(16))
            background = ContextCompat.getDrawable(this@MainActivity, R.drawable.bg_card)
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT,
            ).apply { topMargin = dp(12) }
        }

        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        header.addView(
            TextView(this).apply {
                text = app.nome
                setTextColor(0xFFF2E9E6.toInt())
                textSize = 17f
                setTypeface(typeface, Typeface.BOLD)
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            },
        )
        header.addView(
            TextView(this).apply {
                text = app.categoria.uppercase(Locale("pt", "BR"))
                setTextColor(0xFF49D4FF.toInt())
                textSize = 10f
                letterSpacing = 0.1f
            },
        )
        card.addView(header)

        card.addView(
            TextView(this).apply {
                text = app.resumo
                setTextColor(0xFFC9BABA.toInt())
                textSize = 14f
                setPadding(0, dp(6), 0, 0)
            },
        )

        val tamanho = app.tamanhoMb?.let { String.format(Locale("pt", "BR"), "%.1f MB", it) } ?: "tamanho desconhecido"
        card.addView(
            TextView(this).apply {
                text = "Versão ${app.versaoNome} (build ${app.versaoCodigo}) · $tamanho"
                setTextColor(0xFF8F7C7C.toInt())
                textSize = 12f
                setPadding(0, dp(10), 0, 0)
            },
        )

        val botao = Button(this).apply {
            isAllCaps = false
            stateListAnimator = null
            backgroundTintList = null
            setTextColor(0xFFFFF9F8.toInt())
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT,
            ).apply { topMargin = dp(14) }
        }
        if (!app.disponivel) {
            botao.text = "Em breve"
            botao.isEnabled = false
            botao.background = ContextCompat.getDrawable(this, R.drawable.bg_button_secondary)
        } else {
            botao.text = "Instalar"
            botao.background = ContextCompat.getDrawable(this, R.drawable.bg_button_primary)
            botao.setOnClickListener { instalar(app, botao) }
        }
        card.addView(botao)

        return card
    }

    private fun instalar(app: AppEntry, botao: Button) {
        botao.isEnabled = false
        botao.text = "Baixando..."
        thread {
            try {
                val destino = File(cacheDir, app.arquivo)
                StoreClient.baixarApk(prefs.baseUrl, app.arquivo, destino)
                runOnUiThread {
                    botao.text = "Instalar"
                    botao.isEnabled = true
                    dispararInstalacao(destino)
                }
            } catch (e: Exception) {
                runOnUiThread {
                    botao.text = "Instalar"
                    botao.isEnabled = true
                    Toast.makeText(this, "Falha ao baixar: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    /** Mesma checagem de "instalar apps desconhecidos" do app Companion
     * (ver app_android/app/.../MainActivity.kt:instalarApk) -- sem
     * isso, o ACTION_VIEW abaixo abre uma tela de bloqueio confusa em
     * vez de instalar. */
    private fun dispararInstalacao(arquivo: File) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && !packageManager.canRequestPackageInstalls()) {
            Toast.makeText(
                this, "Autorize \"Instalar apps desconhecidos\" pra essa Loja, e toque em Instalar de novo.",
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
