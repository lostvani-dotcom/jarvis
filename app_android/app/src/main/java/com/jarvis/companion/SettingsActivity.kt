package com.jarvis.companion

import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.jarvis.companion.databinding.ActivitySettingsBinding
import kotlin.concurrent.thread

/**
 * Conexão com o Ultron (IP/porta/token, descoberta automática) e as
 * permissões especiais (notificações, acesso ao uso) -- tudo isso
 * morava direto na tela principal antes; separado pra cá pra
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
            }
        }
    }
}
