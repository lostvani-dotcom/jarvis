package com.jarvis.companion

import android.Manifest
import android.animation.ObjectAnimator
import android.animation.PropertyValuesHolder
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.text.Editable
import android.text.TextWatcher
import android.view.Gravity
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import androidx.recyclerview.widget.LinearLayoutManager
import com.jarvis.companion.databinding.ActivityMainBinding
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.util.Locale
import kotlin.concurrent.thread

/**
 * Tela principal: só o chat, no espírito do ChatGPT mobile -- bolhas
 * de mensagem numa lista rolável (ver ChatAdapter), barra de entrada
 * em formato de pílula, e a engrenagem no topo abre a conexão/
 * permissões numa tela própria (ver SettingsActivity) em vez de
 * misturar tudo na tela principal como antes.
 */
class MainActivity : AppCompatActivity() {

    companion object {
        /** Extra do Intent -- ver VolumeTripleClickService.kt (ativação
         * por hardware: 3 toques no botão de baixar volume abrem o app
         * já ouvindo, sem precisar tocar em nada na tela). */
        const val EXTRA_AUTO_INICIAR_ESCUTA = "auto_iniciar_escuta"
    }

    private lateinit var binding: ActivityMainBinding
    private lateinit var prefs: Prefs
    private lateinit var chatAdapter: ChatAdapter
    private lateinit var sessionsAdapter: SessionsAdapter
    private var speechRecognizer: SpeechRecognizer? = null
    private var tts: TextToSpeech? = null
    private var ultimaEntradaFoiVoz = false
    private var micPulseAnimator: ObjectAnimator? = null
    private var desbloqueado = false

    /** Id da conversa atualmente aberta na tela -- gerado uma vez por
     * "nova conversa" (ou ao abrir o app pela 1ª vez) e reaproveitado a
     * cada autosalvamento, pra sempre atualizar a MESMA entrada em vez
     * de duplicar (ver Sessions.salvar). */
    private var sessaoAtualId: String = Sessions.novoId()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        prefs = Prefs(this)
        // Bloqueio de app: se ligado, esconde tudo e pede a face/digital
        // do dono antes de liberar. Feito logo no onCreate pra o conteúdo
        // nunca aparecer antes da autenticação.
        if (prefs.appLockAtivo && !desbloqueado) {
            binding.root.visibility = View.INVISIBLE
        }

        chatAdapter = ChatAdapter()
        binding.chatRecycler.layoutManager = LinearLayoutManager(this)
        binding.chatRecycler.adapter = chatAdapter

        sessionsAdapter = SessionsAdapter(
            aoTocar = { sessao -> abrirSessao(sessao) },
            aoSegurar = { sessao -> confirmarExclusaoDeSessao(sessao) },
        )
        binding.sessionsRecycler.layoutManager = LinearLayoutManager(this)
        binding.sessionsRecycler.adapter = sessionsAdapter

        binding.menuButton.setOnClickListener {
            binding.drawerLayout.let {
                if (it.isDrawerOpen(Gravity.START)) it.closeDrawer(Gravity.START) else {
                    atualizarListaDeSessoes()
                    it.openDrawer(Gravity.START)
                }
            }
        }
        binding.newChatButton.setOnClickListener { novaConversa() }
        binding.settingsButton.setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
        }
        binding.sendButton.setOnClickListener { enviarMensagem() }
        binding.micButton.setOnClickListener { iniciarEscuta() }
        binding.messageInput.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: Editable?) {
                val temTexto = s?.isNotBlank() == true
                binding.sendButton.alpha = if (temTexto) 1f else 0.5f
            }
        })
        binding.sendButton.alpha = 0.5f

        pedirPermissaoDeNotificacao()
        tts = TextToSpeech(this) { status ->
            if (status == TextToSpeech.SUCCESS) {
                tts?.language = Locale("pt", "BR")
            }
        }

        if (prefs.host.isEmpty() || prefs.token.isEmpty()) {
            adicionarMensagem("Procurando o Ultron na rede automaticamente...", Remetente.SISTEMA)
            buscarAutomaticamente()
        } else {
            adicionarMensagem(
                "Pronto pra conversar. Sem o PC eu já resolvo: bateria, lanterna, " +
                    "volume, não perturbe, brilho, localização, tocar música, abrir app, " +
                    "alarme, timer, ligação, SMS, câmera, pesquisa na web, contas e hora/data " +
                    "(diga \"ajuda\" pra lista completa). Conversa aberta/memória/base de " +
                    "conhecimento precisam do Ultron do PC na mesma rede. Toque no 🎤 pra falar " +
                    "-- a resposta vem por voz também.",
                Remetente.ULTRON,
            )
            checarAtualizacao()
            // Renova a config de IA em silêncio a cada abertura com o PC
            // alcançável -- pega mudança de chave/modelo/personalidade.
            thread {
                JarvisClient.getIaConfig(prefs.baseUrl, prefs.token)?.let { cfg ->
                    prefs.iaBaseUrl = cfg.optString("base_url", "")
                    prefs.iaApiKey = cfg.optString("api_key", "")
                    prefs.iaModelo = cfg.optString("modelo", "")
                    prefs.iaAuthHeader = cfg.optString("auth_header", "Authorization")
                    prefs.iaSystemPrompt = cfg.optString("system_prompt", "")
                }
            }
        }

        // Convida a proteger o app na primeira abertura (depois do
        // onboarding acima) -- só uma vez, sem insistir.
        binding.root.post { oferecerBloqueioApp() }

        // Sem bloqueio ativo, pode escutar assim que a tela abrir; COM
        // bloqueio, só depois de autenticar (ver onStart) -- nunca antes,
        // senão o atalho de hardware furaria o bloqueio do app.
        if (!prefs.appLockAtivo) processarAutoEscuta()
    }

    /** Ver EXTRA_AUTO_INICIAR_ESCUTA -- chamado só uma vez por Intent
     * (limpa o extra depois), pra não reiniciar a escuta sozinho de
     * novo numa rotação de tela ou ao voltar de outra Activity. */
    private fun processarAutoEscuta() {
        if (!intent.getBooleanExtra(EXTRA_AUTO_INICIAR_ESCUTA, false)) return
        intent.removeExtra(EXTRA_AUTO_INICIAR_ESCUTA)
        binding.root.post { iniciarEscuta() }
    }

    override fun onStart() {
        super.onStart()
        // Toda vez que o app volta ao primeiro plano com o bloqueio ligado,
        // exige a autenticação de novo (ex.: deixou aberto e outra pessoa
        // pegou depois). `desbloqueado` só vale enquanto o app fica visível.
        if (prefs.appLockAtivo && !desbloqueado) {
            binding.root.visibility = View.INVISIBLE
            AppLock.autenticar(
                this,
                onSucesso = {
                    desbloqueado = true
                    binding.root.visibility = View.VISIBLE
                    processarAutoEscuta()
                },
                onFalha = {
                    Toast.makeText(this, "Acesso negado.", Toast.LENGTH_SHORT).show()
                    finish()  // fecha o app -- só o dono entra
                },
            )
        }
    }

    override fun onStop() {
        super.onStop()
        // Ao sair de primeiro plano, re-arma o bloqueio pra próxima vez.
        if (prefs.appLockAtivo) desbloqueado = false
    }

    override fun onDestroy() {
        speechRecognizer?.destroy()
        tts?.stop()
        tts?.shutdown()
        super.onDestroy()
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        // Caminho KeyguardManager (Android 8.0-8.1): resultado da tela de
        // credencial do sistema.
        if (AppLock.ehRequestKeyguard(requestCode)) {
            if (AppLock.resultadoKeyguard(requestCode, resultCode)) {
                desbloqueado = true
                binding.root.visibility = View.VISIBLE
            } else {
                Toast.makeText(this, "Acesso negado.", Toast.LENGTH_SHORT).show()
                finish()
            }
        }
    }

    /** Convite (uma vez) pra ligar o bloqueio do app usando a biometria
     * do próprio celular. Chamado depois do onboarding de conexão. Não
     * insiste: se recusar, marca como perguntado e segue. */
    private fun oferecerBloqueioApp() {
        if (prefs.lockSetupPerguntado || prefs.appLockAtivo) return
        prefs.lockSetupPerguntado = true
        if (!AppLock.temBloqueioConfigurado(this)) {
            // Sem face/digital/PIN no celular não dá pra proteger -- guia
            // o usuário a cadastrar primeiro (é lá que "registra a face").
            AlertDialog.Builder(this)
                .setTitle("Proteger o Ultron")
                .setMessage(
                    "Pra deixar que só você abra o Ultron, cadastre uma face ou digital nas " +
                        "configurações de segurança do celular. Depois volte e ative o bloqueio.",
                )
                .setPositiveButton("Abrir configurações") { _, _ ->
                    try {
                        startActivity(Intent(Settings.ACTION_SECURITY_SETTINGS))
                    } catch (e: Exception) {
                        startActivity(Intent(Settings.ACTION_SETTINGS))
                    }
                }
                .setNegativeButton("Agora não", null)
                .show()
            return
        }
        AlertDialog.Builder(this)
            .setTitle("Proteger o Ultron")
            .setMessage(
                "Quer que só você consiga abrir o Ultron? Vou usar a face/digital que já está " +
                    "cadastrada no seu celular -- se outra pessoa tentar abrir, não passa.",
            )
            .setPositiveButton("Ativar bloqueio") { _, _ ->
                prefs.appLockAtivo = true
                desbloqueado = true // acabou de configurar, não trava agora
                Toast.makeText(this, "Bloqueio ativado.", Toast.LENGTH_SHORT).show()
                adicionarMensagem("Bloqueio ativado -- a partir de agora só você me abre.", Remetente.SISTEMA)
            }
            .setNegativeButton("Agora não", null)
            .show()
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 1002 && grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) {
            iniciarEscuta()
        }
    }

    /** Notificações locais (lembrete/observação enquanto o app está
     * fechado -- ver NotificacaoLocal.kt) exigem essa permissão a
     * partir do Android 13 (API 33). Sem ela, o app continua
     * funcionando normalmente, só não mostra esse tipo de aviso. */
    private fun pedirPermissaoDeNotificacao() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED
            ) {
                ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1001)
            }
        }
    }

    /** Manda um broadcast UDP e, se achar o Ultron na rede, já conecta
     * sozinho -- IP, porta e token vêm juntos na resposta (ver
     * Discovery.kt / server/discovery.py) e são salvos e testados na
     * hora, sem precisar tocar em mais nada. */
    private fun buscarAutomaticamente() {
        thread {
            val resultado = Discovery.buscar()
            runOnUiThread {
                if (resultado != null) {
                    prefs.host = resultado.ip
                    prefs.port = resultado.porta.toString()
                    prefs.token = resultado.token
                    adicionarMensagem("Encontrado e conectado em ${resultado.ip}:${resultado.porta}!", Remetente.SISTEMA)
                    checarAtualizacao()
                    sincronizarIaConfig()
                } else {
                    adicionarMensagem(
                        "Não encontrei nenhum Ultron na rede (confirme que ele está rodando, na " +
                            "mesma Wi-Fi). Toque na ⚙ pra configurar IP/porta/token manualmente.",
                        Remetente.SISTEMA,
                    )
                }
            }
        }
    }

    /** Puxa do PC a configuração do provedor de IA sempre que o celular
     * consegue alcançá-lo -- depois disso dá pra CONVERSAR com o Ultron
     * mesmo com o PC desligado (ver CloudAI.kt, "modo nuvem"). Chamado
     * de novo a cada conexão bem-sucedida (não só a primeira vez), pra
     * pegar mudança de chave/modelo/personalidade -- e também em
     * segundo plano por NotifyListenerService, então o modo nuvem se
     * mantém atualizado mesmo sem abrir o app. Melhor-esforço: se o PC
     * não tiver provedor remoto configurado, simplesmente não salva
     * nada e o comportamento antigo continua igual. */
    private fun sincronizarIaConfig() {
        thread {
            val jaEstavaConfigurada = prefs.iaConfigurada
            val cfg = JarvisClient.getIaConfig(prefs.baseUrl, prefs.token) ?: return@thread
            prefs.iaBaseUrl = cfg.optString("base_url", "")
            prefs.iaApiKey = cfg.optString("api_key", "")
            prefs.iaModelo = cfg.optString("modelo", "")
            prefs.iaAuthHeader = cfg.optString("auth_header", "Authorization")
            prefs.iaSystemPrompt = cfg.optString("system_prompt", "")
            prefs.iaUltimaSincronizacao = System.currentTimeMillis()
            // Só avisa na PRIMEIRA vez que fica configurado -- sem essa
            // checagem, toda re-sincronização (bem mais frequente agora)
            // repetiria o mesmo aviso e poluiria o chat.
            if (!jaEstavaConfigurada && prefs.iaConfigurada) {
                runOnUiThread {
                    adicionarMensagem(
                        "Conversa independente ativada -- agora dá pra conversar comigo mesmo com o " +
                            "PC desligado (só preciso de internet no celular).",
                        Remetente.SISTEMA,
                    )
                }
            }
        }
    }

    /** Compara a versão instalada com a que o PC está servindo (GET
     * /app/version) e, se tiver uma mais nova, avisa e oferece pra
     * baixar e instalar sozinho -- sem precisar abrir o navegador e
     * repetir o processo de instalação manual toda vez. */
    private fun checarAtualizacao() {
        thread {
            try {
                val info = JarvisClient.getServerVersion(prefs.baseUrl)
                val versaoServidor = info.optInt("versionCode", 0)
                val nomeServidor = info.optString("versionName", "?")
                val versaoAtual = packageManager.getPackageInfo(packageName, 0).let {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) it.longVersionCode.toInt() else @Suppress("DEPRECATION") it.versionCode
                }
                if (versaoServidor > versaoAtual) {
                    runOnUiThread {
                        adicionarMensagem(
                            "Tem uma atualização do app disponível (versão $nomeServidor). Baixando " +
                                "e instalando sozinho...",
                            Remetente.SISTEMA,
                        )
                    }
                    baixarEInstalarAtualizacao()
                }
            } catch (e: Exception) {
                // melhor-esforço -- sem servidor alcançável, sem checagem de versão
            }
        }
    }

    private fun baixarEInstalarAtualizacao() {
        try {
            val arquivo = File(cacheDir, "jarvis_update.apk")
            val conn = URL("${prefs.baseUrl}/app.apk").openConnection() as HttpURLConnection
            conn.connectTimeout = 8000
            conn.readTimeout = 30000
            conn.inputStream.use { entrada ->
                FileOutputStream(arquivo).use { saida -> entrada.copyTo(saida) }
            }
            runOnUiThread { instalarApk(arquivo) }
        } catch (e: Exception) {
            runOnUiThread {
                adicionarMensagem("Falha ao baixar a atualização (${e.message}).", Remetente.ERRO)
            }
        }
    }

    /** Antes de disparar a instalação, confere se o Android já deixa
     * ESTE app instalar pacotes de fora da Play Store (API 26+, exigido
     * desde o Android 8) -- sem essa permissão especial, o
     * `ACTION_VIEW` do APK abre uma tela de bloqueio confusa em vez de
     * instalar. Preferimos avisar e guiar pra tela certa (mesmo padrão
     * já usado pras outras permissões especiais deste app -- "Não
     * Perturbe", "Acesso ao uso") a deixar o usuário se perguntando por
     * que a atualização "não fez nada". */
    private fun instalarApk(arquivo: File) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && !packageManager.canRequestPackageInstalls()) {
            adicionarMensagem(
                "Preciso da permissão \"Instalar apps desconhecidos\" pra concluir a atualização " +
                    "sozinho -- abrindo a tela pra você autorizar.",
                Remetente.SISTEMA,
            )
            try {
                val i = Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:$packageName"))
                startActivity(i)
            } catch (e: Exception) {
                // melhor-esforço -- se a tela específica não existir neste
                // fabricante, o próprio ACTION_VIEW abaixo ainda tenta e o
                // Android mostra o caminho dele pra essa permissão.
            }
        }
        val uri: Uri = FileProvider.getUriForFile(this, "$packageName.fileprovider", arquivo)
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        startActivity(intent)
    }

    /** Reconhecimento de voz (fala -> texto), via `SpeechRecognizer` nativo do
     * Android (mesmo motor usado pelo teclado/assistente do sistema, sem
     * dependência nova). Pede a permissão de microfone só na hora que o
     * usuário toca no botão pela primeira vez, não no início do app --
     * `onRequestPermissionsResult` retoma a escuta sozinho assim que
     * concedida, sem precisar tocar duas vezes. Entrada por voz sempre
     * vira uma mensagem NATURAL (nunca prefixada com "/"), mesma convenção
     * do modo de comando direto: quem digita pode usar "/", quem fala não
     * precisa -- ver README.md, seção "Modo de comando direto". */
    private fun iniciarEscuta() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
            != PackageManager.PERMISSION_GRANTED
        ) {
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.RECORD_AUDIO), 1002)
            return
        }
        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            Toast.makeText(this, "Reconhecimento de voz não disponível neste aparelho.", Toast.LENGTH_SHORT).show()
            return
        }

        val recognizer = speechRecognizer ?: SpeechRecognizer.createSpeechRecognizer(this).also { speechRecognizer = it }
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "pt-BR")
        }
        recognizer.setRecognitionListener(object : RecognitionListener {
            override fun onReadyForSpeech(params: Bundle?) = animarMicOuvindo(true)
            override fun onBeginningOfSpeech() {}
            override fun onRmsChanged(rmsdB: Float) {}
            override fun onBufferReceived(buffer: ByteArray?) {}
            override fun onEndOfSpeech() = animarMicOuvindo(false)
            override fun onEvent(eventType: Int, params: Bundle?) {}
            override fun onPartialResults(partialResults: Bundle?) {}

            override fun onError(error: Int) {
                animarMicOuvindo(false)
                // ERROR_NO_MATCH/ERROR_SPEECH_TIMEOUT são só "não ouvi nada" --
                // não vale a pena incomodar com um Toast toda vez.
                if (error != SpeechRecognizer.ERROR_NO_MATCH && error != SpeechRecognizer.ERROR_SPEECH_TIMEOUT) {
                    Toast.makeText(this@MainActivity, "Não consegui entender (erro $error).", Toast.LENGTH_SHORT).show()
                }
            }

            override fun onResults(results: Bundle?) {
                animarMicOuvindo(false)
                val texto = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()
                if (!texto.isNullOrBlank()) {
                    ultimaEntradaFoiVoz = true
                    enviarMensagem(texto)
                }
            }
        })
        recognizer.startListening(intent)
    }

    /** Pulso simples de escala no botão do microfone enquanto ouve --
     * único feedback visual de "estou ouvindo" (o Android já mostra o
     * indicador de microfone do sistema, isto aqui é só reforço). */
    private fun animarMicOuvindo(ouvindo: Boolean) {
        if (ouvindo) {
            val pulso = ObjectAnimator.ofPropertyValuesHolder(
                binding.micButton,
                PropertyValuesHolder.ofFloat(View.SCALE_X, 1f, 1.18f, 1f),
                PropertyValuesHolder.ofFloat(View.SCALE_Y, 1f, 1.18f, 1f),
            )
            pulso.duration = 700
            pulso.repeatCount = ObjectAnimator.INFINITE
            micPulseAnimator = pulso
            pulso.start()
        } else {
            micPulseAnimator?.cancel()
            micPulseAnimator = null
            binding.micButton.scaleX = 1f
            binding.micButton.scaleY = 1f
        }
    }

    private fun falarResposta(texto: String) {
        tts?.speak(texto, TextToSpeech.QUEUE_FLUSH, null, "jarvis_resposta")
    }

    private fun enviarMensagem(textoForcado: String? = null) {
        val texto = textoForcado ?: binding.messageInput.text.toString().trim()
        if (texto.isEmpty()) return
        if (textoForcado == null) binding.messageInput.setText("")
        val faladoPorVoz = ultimaEntradaFoiVoz
        ultimaEntradaFoiVoz = false
        adicionarMensagem(texto, Remetente.USUARIO)

        // Comandos de controle do PRÓPRIO celular (bateria, lanterna,
        // volume, não perturbe, brilho, localização, tocar música, hora)
        // são reconhecidos e executados AQUI, sem rede -- funcionam com
        // o Ultron do PC desligado ou fora de alcance. Só o que precisa
        // do "cérebro" (conversa, memória, base de conhecimento, IA,
        // controle do PC) segue pro Ultron do PC como antes.
        val respostaLocal = try {
            LocalCommands.interpretar(applicationContext, texto)
        } catch (e: Exception) {
            null
        }
        if (respostaLocal != null) {
            adicionarMensagem(respostaLocal, Remetente.ULTRON)
            if (faladoPorVoz) falarResposta(respostaLocal)
            return
        }

        thread {
            try {
                val resposta = JarvisClient.chat(prefs.baseUrl, prefs.token, texto)
                runOnUiThread {
                    adicionarMensagem(resposta, Remetente.ULTRON)
                    if (faladoPorVoz) falarResposta(resposta)
                }
            } catch (e: Exception) {
                // PC fora de alcance -- se a config de IA já foi sincronizada
                // alguma vez, conversa DIRETO com a nuvem (CloudAI.kt), sem
                // o PC. Só cai na mensagem de erro se os dois caminhos
                // falharem (ex.: celular sem internet nenhuma).
                if (prefs.iaConfigurada) {
                    try {
                        val resposta = CloudAI.conversar(prefs, texto)
                        runOnUiThread {
                            // "☁" no início -- só um sinal discreto de que essa
                            // resposta veio do modo nuvem (sem memória/plugins do
                            // PC), não uma etiqueta gritante.
                            adicionarMensagem("☁ $resposta", Remetente.ULTRON)
                            if (faladoPorVoz) falarResposta(resposta)
                        }
                        return@thread
                    } catch (e2: Exception) {
                        runOnUiThread {
                            adicionarMensagem(
                                "PC fora de alcance e a conversa direta com a nuvem também falhou " +
                                    "(${e2.message}) -- confira a internet do celular. Comandos do " +
                                    "aparelho seguem funcionando: diga \"ajuda\".",
                                Remetente.ERRO,
                            )
                        }
                        return@thread
                    }
                }
                runOnUiThread {
                    adicionarMensagem(
                        "Isso precisa do Ultron rodando no PC (mesma rede) -- não consegui alcançar " +
                            "(${e.message}). Comandos do próprio celular funcionam mesmo assim: diga " +
                            "\"ajuda\" pra ver a lista. Pra conversar sem o PC, conecte uma vez com o " +
                            "PC ligado que eu ativo a conversa independente.",
                        Remetente.ERRO,
                    )
                }
            }
        }
    }

    private fun adicionarMensagem(texto: String, remetente: Remetente) {
        chatAdapter.adicionar(texto, remetente)
        binding.chatRecycler.post {
            binding.chatRecycler.scrollToPosition(chatAdapter.itemCount - 1)
        }
        autosalvarSessaoAtual()
    }

    /** Salva (ou atualiza) a conversa da tela na lista de sessões
     * locais a cada mensagem -- assim fechar o app no meio de uma
     * conversa não perde nada, sem precisar de um botão "salvar"
     * manual. Mensagens só de SISTEMA/ERRO (sem nenhuma do usuário)
     * não geram entrada -- ver Sessions.salvar. */
    private fun autosalvarSessaoAtual() {
        Sessions.salvar(applicationContext, sessaoAtualId, chatAdapter.todasAsMensagens())
    }

    private fun atualizarListaDeSessoes() {
        val sessoes = Sessions.listar(applicationContext)
        sessionsAdapter.atualizar(sessoes)
        binding.emptySessionsText.visibility = if (sessoes.isEmpty()) View.VISIBLE else View.GONE
    }

    /** Abre uma conversa salva no painel: substitui o que está na tela
     * por ela e passa a autosalvar NELA (id reaproveitado) -- mandar
     * uma mensagem nova continua essa mesma conversa, igual o ChatGPT
     * faz ao reabrir um tópico antigo. Isso é só sobre qual transcript
     * aparece no celular; a memória do Ultron no PC não muda com isso. */
    private fun abrirSessao(sessao: ChatSession) {
        sessaoAtualId = sessao.id
        chatAdapter.substituirTudo(sessao.mensagens)
        binding.chatRecycler.post {
            binding.chatRecycler.scrollToPosition(maxOf(0, chatAdapter.itemCount - 1))
        }
        binding.drawerLayout.closeDrawer(Gravity.START)
    }

    /** Guarda a conversa atual (se tiver algo) e começa uma em branco,
     * com um id novo -- mesmo espírito do botão "+" do ChatGPT. */
    private fun novaConversa() {
        autosalvarSessaoAtual()
        sessaoAtualId = Sessions.novoId()
        chatAdapter.substituirTudo(emptyList())
        binding.drawerLayout.closeDrawer(Gravity.START)
        adicionarMensagem("Nova conversa. Pode mandar.", Remetente.SISTEMA)
    }

    private fun confirmarExclusaoDeSessao(sessao: ChatSession) {
        AlertDialog.Builder(this)
            .setTitle("Excluir conversa")
            .setMessage("Apagar \"${sessao.titulo}\" da lista? Isso só remove o transcript salvo neste celular -- não mexe na memória do Ultron no PC.")
            .setPositiveButton("Excluir") { _, _ ->
                Sessions.excluir(applicationContext, sessao.id)
                if (sessao.id == sessaoAtualId) {
                    sessaoAtualId = Sessions.novoId()
                }
                atualizarListaDeSessoes()
            }
            .setNegativeButton("Cancelar", null)
            .show()
    }
}
