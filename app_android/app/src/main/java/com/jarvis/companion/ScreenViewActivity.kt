package com.jarvis.companion

import android.graphics.BitmapFactory
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.jarvis.companion.databinding.ActivityScreenViewBinding
import kotlin.concurrent.thread

/** "Ver a tela do PC" -- não é VNC de verdade (sem controle remoto,
 * só visualização), mas resolve o caso de uso real: checar se o
 * Ultron está rodando/travado sem precisar estar na frente da
 * máquina. Busca um screenshot novo (GET /tela/atual, JPEG) num
 * polling curto enquanto a tela estiver visível -- simples o
 * bastante pra não precisar de WebSocket/streaming de verdade. */
class ScreenViewActivity : AppCompatActivity() {

    private lateinit var binding: ActivityScreenViewBinding
    private lateinit var prefs: Prefs
    private val handler = Handler(Looper.getMainLooper())
    private var ativo = false
    private var buscando = false
    private val intervaloMs = 1500L

    private val pollingRunnable = object : Runnable {
        override fun run() {
            if (!ativo) return
            buscarScreenshot()
            handler.postDelayed(this, intervaloMs)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityScreenViewBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = Prefs(this)

        binding.backButton.setOnClickListener { finish() }

        if (prefs.host.isEmpty() || prefs.token.isEmpty()) {
            binding.statusText.text = "Configure a conexão com o Ultron do PC primeiro."
            Toast.makeText(this, "Sem conexão configurada.", Toast.LENGTH_LONG).show()
            return
        }
    }

    override fun onStart() {
        super.onStart()
        if (prefs.host.isEmpty() || prefs.token.isEmpty()) return
        ativo = true
        handler.post(pollingRunnable)
    }

    override fun onStop() {
        super.onStop()
        ativo = false
        handler.removeCallbacks(pollingRunnable)
    }

    private fun buscarScreenshot() {
        if (buscando) return  // não empilha pedidos se um anterior ainda não voltou
        buscando = true
        thread {
            try {
                val bytes = JarvisClient.getScreenshot(prefs.baseUrl, prefs.token)
                val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
                runOnUiThread {
                    if (bitmap != null) {
                        binding.screenImage.setImageBitmap(bitmap)
                        binding.statusText.text = "Tela do PC (atualizando a cada ${intervaloMs / 1000}s)"
                    }
                    buscando = false
                }
            } catch (e: Exception) {
                runOnUiThread {
                    binding.statusText.text = "Não consegui buscar a tela (${e.message})."
                    buscando = false
                }
            }
        }
    }
}
