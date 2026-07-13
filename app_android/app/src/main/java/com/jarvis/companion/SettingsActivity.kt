package com.jarvis.companion

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.provider.MediaStore
import android.provider.Settings
import android.view.LayoutInflater
import android.widget.Chronometer
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import com.jarvis.companion.databinding.ActivitySettingsBinding
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.concurrent.thread

/**
 * Conexão com o Ultron (IP/porta/token, descoberta automática), as
 * permissões especiais (notificações, acesso ao uso) e o status do
 * "modo nuvem" (conversar sem o PC ligado, ver CloudAI.kt) -- tudo
 * isso morava direto na tela principal antes; separado pra cá pra
 * MainActivity ficar só o chat (mesmo espírito do ChatGPT: a tela
 * principal é só a conversa, configuração fica atrás de um ícone).
 */
class SettingsActivity : AppCompatActivity() {

    private lateinit var binding: ActivitySettingsBinding
    private lateinit var prefs: Prefs
    private var gravador: VoiceSampleRecorder? = null
    private var dialogoGravacao: AlertDialog? = null
    private var fotoRostoArquivo: File? = null

    companion object {
        private const val REQ_AUDIO = 3001
        private const val REQ_FOTO_ROSTO = 3002
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivitySettingsBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = Prefs(this)

        binding.hostInput.setText(prefs.host)
        binding.portInput.setText(prefs.port)
        binding.tokenInput.setText(prefs.token)

        binding.backButton.setOnClickListener { finish() }
        binding.discoverButton.setOnClickListener { buscarAutomaticamente() }
        binding.saveButton.setOnClickListener {
            prefs.host = binding.hostInput.text.toString().trim()
            prefs.port = binding.portInput.text.toString().trim().ifEmpty { "8765" }
            prefs.token = binding.tokenInput.text.toString().trim()
            testarConexao()
        }
        binding.notificationAccessButton.setOnClickListener {
            startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
        }
        binding.usageAccessButton.setOnClickListener {
            startActivity(Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS))
        }
        binding.cloudSyncButton.setOnClickListener { sincronizarNuvem() }
        binding.cloudForgetButton.setOnClickListener { confirmarEsquecerNuvem() }
        binding.recordVoiceSampleButton.setOnClickListener { pedirPermissaoDeAudioEGravar() }
        binding.identifyFaceButton.setOnClickListener { abrirCameraParaIdentificar() }
        binding.screenViewButton.setOnClickListener { abrirVisualizacaoDeTela() }
        binding.hardwareShortcutButton.setOnClickListener {
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        }
        binding.statsButton.setOnClickListener { buscarEstatisticas() }

        atualizarStatusNuvem()
    }

    override fun onResume() {
        super.onResume()
        atualizarStatusNuvem()  // pega mudança feita em segundo plano (NotifyListenerService)
    }

    private fun atualizarStatusNuvem() {
        binding.cloudStatusText.text = if (prefs.iaConfigurada) {
            val quando = prefs.iaUltimaSincronizacao
            val quandoTexto = if (quando > 0) {
                SimpleDateFormat("dd/MM HH:mm", Locale("pt", "BR")).format(Date(quando))
            } else {
                "nunca"
            }
            "Ativo -- modelo \"${prefs.iaModelo}\"\nÚltima sincronização: $quandoTexto"
        } else {
            "Ainda não configurado -- conecte com o Ultron do PC ligado pelo menos uma vez " +
                "(com um provedor de IA remoto configurado nele) pra ativar."
        }
    }

    private fun buscarAutomaticamente() {
        binding.discoverButton.isEnabled = false
        binding.discoverButton.text = "Procurando..."
        thread {
            val resultado = Discovery.buscar()
            runOnUiThread {
                binding.discoverButton.isEnabled = true
                binding.discoverButton.text = "Buscar o Ultron automaticamente"
                if (resultado != null) {
                    binding.hostInput.setText(resultado.ip)
                    binding.portInput.setText(resultado.porta.toString())
                    binding.tokenInput.setText(resultado.token)
                    prefs.host = resultado.ip
                    prefs.port = resultado.porta.toString()
                    prefs.token = resultado.token
                    Toast.makeText(this, "Conectado ao Ultron!", Toast.LENGTH_SHORT).show()
                    sincronizarNuvem()
                } else {
                    Toast.makeText(
                        this, "Não encontrei o Ultron na rede -- confira se ele está rodando, na mesma Wi-Fi.",
                        Toast.LENGTH_LONG,
                    ).show()
                }
            }
        }
    }

    private fun testarConexao() {
        thread {
            val ok = JarvisClient.status(prefs.baseUrl)
            runOnUiThread {
                Toast.makeText(
                    this,
                    if (ok) "Conectado ao Ultron!" else "Não consegui alcançar o Ultron nesse endereço.",
                    Toast.LENGTH_SHORT,
                ).show()
                if (ok) sincronizarNuvem()
            }
        }
    }

    /** Busca a config de IA do PC na hora (mesma lógica de
     * MainActivity.sincronizarIaConfig) -- pra quando o usuário quer
     * forçar a atualização em vez de esperar a sincronização automática
     * (aberturas do app / polling em segundo plano). */
    private fun sincronizarNuvem() {
        binding.cloudSyncButton.isEnabled = false
        thread {
            val cfg = JarvisClient.getIaConfig(prefs.baseUrl, prefs.token)
            runOnUiThread {
                binding.cloudSyncButton.isEnabled = true
                if (cfg == null) {
                    Toast.makeText(
                        this, "Não consegui sincronizar -- confira se o Ultron do PC está ligado e alcançável.",
                        Toast.LENGTH_LONG,
                    ).show()
                    return@runOnUiThread
                }
                prefs.iaBaseUrl = cfg.optString("base_url", "")
                prefs.iaApiKey = cfg.optString("api_key", "")
                prefs.iaModelo = cfg.optString("modelo", "")
                prefs.iaAuthHeader = cfg.optString("auth_header", "Authorization")
                prefs.iaSystemPrompt = cfg.optString("system_prompt", "")
                prefs.iaUltimaSincronizacao = System.currentTimeMillis()
                atualizarStatusNuvem()
                Toast.makeText(
                    this,
                    if (prefs.iaConfigurada) "Modo nuvem sincronizado!" else "PC alcançado, mas sem provedor de IA remoto configurado nele.",
                    Toast.LENGTH_SHORT,
                ).show()
            }
        }
    }

    private fun confirmarEsquecerNuvem() {
        AlertDialog.Builder(this)
            .setTitle("Esquecer conversa da nuvem")
            .setMessage("Isso apaga o histórico da conversa independente (modo nuvem), guardado só neste celular. Não afeta a memória do Ultron no PC. Confirma?")
            .setPositiveButton("Esquecer") { _, _ ->
                CloudAI.limparHistorico(prefs)
                Toast.makeText(this, "Conversa da nuvem esquecida.", Toast.LENGTH_SHORT).show()
            }
            .setNegativeButton("Cancelar", null)
            .show()
    }

    // ---- Gravar amostra de voz pelo celular (clonagem, ver VoiceSampleRecorder) ----

    private fun pedirPermissaoDeAudioEGravar() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
            != PackageManager.PERMISSION_GRANTED
        ) {
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.RECORD_AUDIO), REQ_AUDIO)
            return
        }
        iniciarGravacaoDeAmostra()
    }

    private fun iniciarGravacaoDeAmostra() {
        if (prefs.host.isEmpty() || prefs.token.isEmpty()) {
            Toast.makeText(this, "Configure a conexão com o Ultron do PC primeiro.", Toast.LENGTH_LONG).show()
            return
        }
        val view = LayoutInflater.from(this).inflate(R.layout.dialog_gravar_voz, null)
        val cronometro = view.findViewById<Chronometer>(R.id.recordChronometer)

        val rec = VoiceSampleRecorder(applicationContext)
        try {
            rec.iniciar()
        } catch (e: Exception) {
            Toast.makeText(this, "Não consegui usar o microfone (${e.message}).", Toast.LENGTH_LONG).show()
            return
        }
        gravador = rec
        cronometro.base = android.os.SystemClock.elapsedRealtime()
        cronometro.start()

        dialogoGravacao = AlertDialog.Builder(this)
            .setView(view)
            .setPositiveButton("Parar e enviar") { _, _ -> pararEEnviarAmostra() }
            .setNegativeButton("Cancelar") { _, _ -> gravador?.cancelar(); gravador = null }
            .setCancelable(false)
            .show()
    }

    private fun pararEEnviarAmostra() {
        val arquivo = gravador?.parar()
        gravador = null
        if (arquivo == null || !arquivo.exists() || arquivo.length() == 0L) {
            Toast.makeText(this, "Gravação vazia demais -- tente falar por mais tempo.", Toast.LENGTH_LONG).show()
            return
        }
        Toast.makeText(this, "Enviando amostra pro Ultron do PC...", Toast.LENGTH_SHORT).show()
        thread {
            try {
                JarvisClient.enviarAmostraVoz(prefs.baseUrl, prefs.token, arquivo)
                runOnUiThread {
                    Toast.makeText(
                        this,
                        "Amostra enviada! Diga \"clonar minha voz\" pro Ultron do PC pra treinar com ela.",
                        Toast.LENGTH_LONG,
                    ).show()
                }
            } catch (e: Exception) {
                runOnUiThread {
                    Toast.makeText(this, "Falha ao enviar (${e.message}).", Toast.LENGTH_LONG).show()
                }
            } finally {
                arquivo.delete()
            }
        }
    }

    // ---- Identificar rosto pela câmera do celular (ver visao/faces.py) ----

    private fun abrirCameraParaIdentificar() {
        if (prefs.host.isEmpty() || prefs.token.isEmpty()) {
            Toast.makeText(this, "Configure a conexão com o Ultron do PC primeiro.", Toast.LENGTH_LONG).show()
            return
        }
        val arquivo = File(cacheDir, "foto_rosto.jpg")
        fotoRostoArquivo = arquivo
        val uri = FileProvider.getUriForFile(this, "$packageName.fileprovider", arquivo)
        val intent = Intent(MediaStore.ACTION_IMAGE_CAPTURE).apply {
            putExtra(MediaStore.EXTRA_OUTPUT, uri)
            addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
        }
        try {
            startActivityForResult(intent, REQ_FOTO_ROSTO)
        } catch (e: Exception) {
            Toast.makeText(this, "Não achei um app de câmera neste aparelho.", Toast.LENGTH_LONG).show()
        }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQ_FOTO_ROSTO && resultCode == RESULT_OK) {
            enviarFotoParaIdentificar()
        }
    }

    private fun enviarFotoParaIdentificar() {
        val arquivo = fotoRostoArquivo ?: return
        if (!arquivo.exists() || arquivo.length() == 0L) {
            Toast.makeText(this, "Não recebi a foto -- tente de novo.", Toast.LENGTH_SHORT).show()
            return
        }
        binding.faceResultText.visibility = android.view.View.VISIBLE
        binding.faceResultText.text = "Identificando..."
        thread {
            try {
                val bytes = arquivo.readBytes()
                val rostos = JarvisClient.identificarRosto(prefs.baseUrl, prefs.token, bytes)
                runOnUiThread {
                    binding.faceResultText.text = if (rostos.length() == 0) {
                        "Nenhum rosto reconhecido nessa foto."
                    } else {
                        val linhas = (0 until rostos.length()).joinToString("\n") { i ->
                            val r = rostos.getJSONObject(i)
                            val nome = r.optString("nome", "?")
                            "• $nome"
                        }
                        "Reconhecido:\n$linhas"
                    }
                }
            } catch (e: Exception) {
                runOnUiThread {
                    binding.faceResultText.text = "Falha ao identificar (${e.message})."
                }
            } finally {
                arquivo.delete()
            }
        }
    }

    // ---- Extras: ver tela do PC, atalho de hardware, estatísticas de uso ----

    private fun abrirVisualizacaoDeTela() {
        if (prefs.host.isEmpty() || prefs.token.isEmpty()) {
            Toast.makeText(this, "Configure a conexão com o Ultron do PC primeiro.", Toast.LENGTH_LONG).show()
            return
        }
        startActivity(Intent(this, ScreenViewActivity::class.java))
    }

    private fun buscarEstatisticas() {
        if (prefs.host.isEmpty() || prefs.token.isEmpty()) {
            Toast.makeText(this, "Configure a conexão com o Ultron do PC primeiro.", Toast.LENGTH_LONG).show()
            return
        }
        binding.statsResultText.visibility = android.view.View.VISIBLE
        binding.statsResultText.text = "Buscando..."
        thread {
            try {
                val dados = JarvisClient.getEstatisticas(prefs.baseUrl, prefs.token, 7)
                val total = dados.optInt("total_mensagens", 0)
                val dias = dados.optInt("dias", 7)
                val top = dados.optJSONArray("top_comandos")
                runOnUiThread {
                    if (total == 0) {
                        binding.statsResultText.text = "Não processei nenhuma mensagem nos últimos $dias dia(s)."
                        return@runOnUiThread
                    }
                    val linhas = StringBuilder("Últimos $dias dia(s): $total mensagem(ns) processada(s).\n")
                    if (top != null) {
                        linhas.append("Mais usados:\n")
                        for (i in 0 until top.length()) {
                            val item = top.getJSONObject(i)
                            linhas.append("- ${item.optString("rotulo")}: ${item.optInt("vezes")}x\n")
                        }
                    }
                    binding.statsResultText.text = linhas.toString().trim()
                }
            } catch (e: Exception) {
                runOnUiThread {
                    binding.statsResultText.text = "Falha ao buscar estatísticas (${e.message})."
                }
            }
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQ_AUDIO && grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) {
            iniciarGravacaoDeAmostra()
        }
    }

    override fun onDestroy() {
        gravador?.cancelar()
        dialogoGravacao?.dismiss()
        super.onDestroy()
    }
}
