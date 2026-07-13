package com.jarvis.companion

import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import com.jarvis.companion.databinding.ActivitySettingsBinding
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
}
