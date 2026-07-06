package com.jarvis.companion

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.AlarmClock
import android.provider.MediaStore
import android.provider.Settings
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Comandos que o app reconhece e executa SOZINHO, sem precisar do
 * Jarvis do PC ligado nem de rede nenhuma -- tudo aqui já existia como
 * capacidade do celular via DeviceCommands.kt, que antes só rodava
 * quando o PC EMPURRAVA o comando pro celular (polling em
 * NotifyListenerService). Esta camada reconhece a intenção localmente
 * (regex simples em português, sem IA nenhuma) e chama a MESMA função
 * de execução, offline -- é por isso que "liga a lanterna"/"bateria"/
 * "toca uma música" continuam funcionando com o Ultron do PC desligado.
 *
 * Honestidade sobre o escopo: perguntas abertas, memória, base de
 * conhecimento, e controle do PC continuam exigindo o Ultron do PC
 * ligado e alcançável na rede -- não existe (nem faria sentido tentar
 * embutir aqui) um cérebro de IA completo no celular. O que passa a
 * funcionar 100% offline é controle do PRÓPRIO celular: abrir apps,
 * bateria, lanterna, volume, não perturbe, modo de toque, brilho,
 * localização, armazenamento, consumo de dados, status da rede, tocar
 * música, hora/data.
 *
 * `interpretar()` retorna null se não reconheceu nada localmente --
 * MainActivity então cai pro caminho de sempre (JarvisClient.chat, que
 * precisa do PC), e só aí a mensagem "isso precisa do Ultron no PC"
 * aparece se a rede falhar.
 */
object LocalCommands {

    private val ABRIR_APP = Regex("""^\s*(?:abre|abrir|abra)\s+(?:o|a)?\s*(.+)""", RegexOption.IGNORE_CASE)
    private val BATERIA_DETALHE = Regex(
        """\b(sa[uú]de|temperatura|voltagem)\b.*\bbateria\b|\bbateria\b.*\b(sa[uú]de|temperatura|voltagem)\b""",
        RegexOption.IGNORE_CASE,
    )
    private val BATERIA = Regex("""\bbateria\b""", RegexOption.IGNORE_CASE)
    private val LANTERNA_ON = Regex("""\b(liga|ligue|acende|acenda)\w*\s+.*\blanterna\b""", RegexOption.IGNORE_CASE)
    private val LANTERNA_OFF = Regex("""\b(desliga|desligue|apaga|apague)\w*\s+.*\blanterna\b""", RegexOption.IGNORE_CASE)
    private val VOLUME_UP = Regex("""\b(aumenta|aumente|sobe|suba)\w*\s+.*\bvolume\b""", RegexOption.IGNORE_CASE)
    private val VOLUME_DOWN = Regex("""\b(diminui|diminua|abaixa|abaixe|baixa)\w*\s+.*\bvolume\b""", RegexOption.IGNORE_CASE)
    private val VOLUME_MUTE = Regex("""\bmut[ae]\w*\b""", RegexOption.IGNORE_CASE)
    private val DND_ON = Regex("""\b(ativ[ae]|lig[ae])\w*\s+.*\bn[aã]o\s+perturbe\b""", RegexOption.IGNORE_CASE)
    private val DND_OFF = Regex("""\b(desativ[ae]|deslig[ae])\w*\s+.*\bn[aã]o\s+perturbe\b""", RegexOption.IGNORE_CASE)
    private val MODO_SILENCIOSO = Regex("""\bmodo\s+silencioso\b|\bcoloca\w*\s+.*\bsilencioso\b""", RegexOption.IGNORE_CASE)
    private val MODO_VIBRAR = Regex("""\bmodo\s+vibra\w*\b|\bcoloca\w*\s+.*\bvibra\w*\b""", RegexOption.IGNORE_CASE)
    private val MODO_NORMAL = Regex("""\bmodo\s+normal\b|\btoque\s+normal\b""", RegexOption.IGNORE_CASE)
    private val BRILHO = Regex("""\bbrilho\b.*?(\d{1,3})""", RegexOption.IGNORE_CASE)
    private val LOCALIZACAO = Regex("""\blocaliza[çc][ãa]o\b|\bonde\s+(?:eu\s+)?(?:estou|to|tô)\b""", RegexOption.IGNORE_CASE)
    private val ARMAZENAMENTO = Regex("""\barmazenamento\b|\bespa[çc]o\s+livre\b""", RegexOption.IGNORE_CASE)
    private val CONSUMO_DADOS = Regex("""\bconsumo\s+de\s+dados\b|\bquanto\s+de\s+dados\b""", RegexOption.IGNORE_CASE)
    private val STATUS_REDE = Regex("""\bstatus\s+da\s+rede\b|\bestou\s+conectad[oa]\s+(?:em|no|na)\b""", RegexOption.IGNORE_CASE)
    private val HORAS = Regex("""\bque\s+horas?\s+(?:s[ãa]o|é)\b""", RegexOption.IGNORE_CASE)
    private val DATA = Regex("""\bque\s+dia\s+é\s+hoje\b|\bdata\s+de\s+hoje\b""", RegexOption.IGNORE_CASE)
    private val TOCAR = Regex(
        """\b(?:toc[ae]\w*|coloc[ae]\w*|põe|poe|bota)\b\s+(?:a\s+m[úu]sica\s+|a\s+|o\s+|umas?\s+)?(.+)""",
        RegexOption.IGNORE_CASE,
    )
    private val SERVICO_SPOTIFY = Regex("""\b(?:no|pelo)\s+spotify\b""", RegexOption.IGNORE_CASE)
    private val SERVICO_YOUTUBE = Regex("""\b(?:no|pelo)\s+youtube\b""", RegexOption.IGNORE_CASE)

    // ---- capacidades novas, todas 100% offline (intents do Android) ----
    private val SAUDACAO = Regex("""^\s*(?:oi+|ol[áa]|e\s*a[íi]|eai|fala)\s*[!.,]*\s*$""", RegexOption.IGNORE_CASE)
    private val BOM_DIA = Regex("""^\s*bo[am]\s+(dia|tarde|noite)\b""", RegexOption.IGNORE_CASE)
    private val TUDO_BEM = Regex("""\btudo\s+bem\b|\bcomo\s+(?:vai|est[áa]|c[êe]\s+t[áa])\b""", RegexOption.IGNORE_CASE)
    private val OBRIGADO = Regex("""^\s*(?:obrigad[oa]+|valeu|vlw)\b""", RegexOption.IGNORE_CASE)
    private val QUEM_E = Regex("""\bquem\s+[ée]\s+voc[êe]\b|\bvoc[êe]\s+[ée]\s+quem\b""", RegexOption.IGNORE_CASE)
    private val AJUDA = Regex("""^\s*(?:ajuda|help|o\s+que\s+voc[êe]\s+faz)\s*[?!.]*\s*$""", RegexOption.IGNORE_CASE)
    private val ALARME = Regex(
        """\b(?:alarme|despertador|me\s+acorda\w*)\b.*?(\d{1,2})(?:[:h](\d{2}))?\b""",
        RegexOption.IGNORE_CASE,
    )
    private val TIMER = Regex(
        """\b(?:timer|temporizador|cron[oô]metro)\b.*?(\d+)\s*(horas?|minutos?|min\b|segundos?|s\b)""",
        RegexOption.IGNORE_CASE,
    )
    // exige dígitos de verdade -- "liga a lanterna"/"liga pra maria" nunca caem aqui
    private val LIGAR_NUMERO = Regex(
        """\b(?:lig[aue]\w*|chama)\s+(?:pra|para)\s+(?:o\s+n[úu]mero\s+)?([\d\s()+-]{8,})""",
        RegexOption.IGNORE_CASE,
    )
    private val SMS = Regex(
        """\bsms\s+(?:pra|para)\s+([\d\s()+-]{8,}?)(?:\s+dizendo\s+(.+))?\s*$""",
        RegexOption.IGNORE_CASE,
    )
    private val CAMERA = Regex("""\b(?:abr[ae]\w*|lig[ae]\w*)\s+.*\bc[âa]mera\b""", RegexOption.IGNORE_CASE)
    private val CONFIG_WIFI = Regex("""\b(?:configura[çc][õo]\w*|ajustes?|painel)\s+d?[eo]?\s*wi-?fi\b|\bwi-?fi\b.*\bconfigura""", RegexOption.IGNORE_CASE)
    private val CONFIG_BLUETOOTH = Regex("""\bbluetooth\b""", RegexOption.IGNORE_CASE)
    private val PESQUISA = Regex("""^\s*(?:pesquis[ae]\w*|procur[ae]\w*|busc[ae]\w*)\s+(?:por\s+|sobre\s+)?(.+)""", RegexOption.IGNORE_CASE)
    private val PORCENTAGEM = Regex(
        """quanto\s+[ée]\s+(\d+(?:[.,]\d+)?)\s*%\s*de\s+(\d+(?:[.,]\d+)?)""",
        RegexOption.IGNORE_CASE,
    )
    private val CONTA = Regex(
        """quanto\s+[ée]\s+(\d+(?:[.,]\d+)?)\s*([-+xX*/÷])\s*(\d+(?:[.,]\d+)?)""",
        RegexOption.IGNORE_CASE,
    )

    /** Retorna a resposta se reconheceu e executou algo localmente, ou
     * null se não reconheceu nada (MainActivity cai pro Ultron do PC). */
    fun interpretar(context: Context, textoOriginal: String): String? {
        val t = textoOriginal.trim()
        if (t.isEmpty()) return null

        // Conversa básica local -- sem isso, um simples "oi" com o PC
        // desligado virava mensagem de erro de rede, parecendo quebrado.
        // Os padrões soltos (tudo bem/obrigado/quem é você) só valem pra
        // mensagens CURTAS: numa frase longa, "tudo bem" costuma ser parte
        // de outra coisa ("sms pra X dizendo tudo bem") e não a saudação.
        val curto = t.length <= 30
        if (SAUDACAO.containsMatchIn(t)) return "Oi. No que posso ajudar?"
        BOM_DIA.find(t)?.let { m ->
            return "Bo" + (if (m.groupValues[1].lowercase() == "dia") "m" else "a") +
                " ${m.groupValues[1].lowercase()}. Pronto pra começar."
        }
        if (curto && TUDO_BEM.containsMatchIn(t)) return "Funcionando em capacidade total. E você?"
        if (curto && OBRIGADO.containsMatchIn(t)) return "De nada. Algo mais?"
        if (curto && QUEM_E.containsMatchIn(t)) {
            return "Sou o Ultron, seu assistente. Aqui no celular executo comandos do aparelho " +
                "mesmo sem o PC; conversas abertas e memória precisam do Ultron do PC na mesma rede."
        }
        if (AJUDA.containsMatchIn(t)) {
            return "Sem precisar do PC eu consigo: bateria, lanterna, volume, não perturbe, " +
                "modo silencioso/vibrar, brilho, localização, armazenamento, consumo de dados, " +
                "status da rede, abrir apps, tocar música, alarme (\"alarme pra 7:30\"), timer " +
                "(\"timer de 10 minutos\"), ligação (\"liga pra <número>\"), SMS (\"sms pra " +
                "<número> dizendo ...\"), câmera, pesquisa na web, contas (\"quanto é 15% de " +
                "200\") e hora/data. O resto eu encaminho pro Ultron do PC."
        }

        if (HORAS.containsMatchIn(t)) {
            return "Agora são " + SimpleDateFormat("HH:mm", Locale("pt", "BR")).format(Date()) + "."
        }
        if (DATA.containsMatchIn(t)) {
            return "Hoje é " + SimpleDateFormat("dd/MM/yyyy", Locale("pt", "BR")).format(Date()) + "."
        }

        PORCENTAGEM.find(t)?.let { m ->
            val a = m.groupValues[1].replace(",", ".").toDoubleOrNull() ?: return@let
            val b = m.groupValues[2].replace(",", ".").toDoubleOrNull() ?: return@let
            return "${numero(a)}% de ${numero(b)} é ${numero(a / 100.0 * b)}."
        }
        CONTA.find(t)?.let { m ->
            val a = m.groupValues[1].replace(",", ".").toDoubleOrNull() ?: return@let
            val b = m.groupValues[3].replace(",", ".").toDoubleOrNull() ?: return@let
            val op = m.groupValues[2]
            val res = when (op) {
                "+" -> a + b
                "-" -> a - b
                "x", "X", "*" -> a * b
                else -> if (b == 0.0) return "Divisão por zero não dá." else a / b
            }
            return "${numero(a)} $op ${numero(b)} = ${numero(res)}"
        }

        ALARME.find(t)?.let { m ->
            val hora = m.groupValues[1].toIntOrNull() ?: return@let
            if (hora > 23) return@let
            val minuto = m.groupValues[2].toIntOrNull() ?: 0
            return try {
                val i = Intent(AlarmClock.ACTION_SET_ALARM)
                    .putExtra(AlarmClock.EXTRA_HOUR, hora)
                    .putExtra(AlarmClock.EXTRA_MINUTES, minuto)
                    .putExtra(AlarmClock.EXTRA_MESSAGE, "Ultron")
                    .putExtra(AlarmClock.EXTRA_SKIP_UI, true)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                context.startActivity(i)
                "Alarme criado para %02d:%02d.".format(hora, minuto)
            } catch (e: Exception) {
                "Não consegui criar o alarme: ${e.message}"
            }
        }
        TIMER.find(t)?.let { m ->
            val valor = m.groupValues[1].toIntOrNull() ?: return@let
            val unidade = m.groupValues[2].lowercase()
            val segundos = when {
                unidade.startsWith("hora") -> valor * 3600
                unidade.startsWith("min") -> valor * 60
                else -> valor
            }
            return try {
                val i = Intent(AlarmClock.ACTION_SET_TIMER)
                    .putExtra(AlarmClock.EXTRA_LENGTH, segundos)
                    .putExtra(AlarmClock.EXTRA_MESSAGE, "Ultron")
                    .putExtra(AlarmClock.EXTRA_SKIP_UI, true)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                context.startActivity(i)
                "Timer de $valor $unidade iniciado."
            } catch (e: Exception) {
                "Não consegui criar o timer: ${e.message}"
            }
        }
        LIGAR_NUMERO.find(t)?.let { m ->
            val numero = m.groupValues[1].filter { it.isDigit() || it == '+' }
            return try {
                // ACTION_DIAL (não ACTION_CALL): abre o discador com o número
                // pronto e VOCÊ aperta ligar -- sem permissão de telefone e
                // sem risco de uma ligação disparada por engano.
                context.startActivity(
                    Intent(Intent.ACTION_DIAL, Uri.parse("tel:$numero")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                )
                "Discador aberto com $numero -- é só confirmar a ligação."
            } catch (e: Exception) {
                "Não consegui abrir o discador: ${e.message}"
            }
        }
        SMS.find(t)?.let { m ->
            val numero = m.groupValues[1].filter { it.isDigit() || it == '+' }
            val corpo = m.groupValues[2]
            return try {
                val i = Intent(Intent.ACTION_SENDTO, Uri.parse("smsto:$numero")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                if (corpo.isNotBlank()) i.putExtra("sms_body", corpo)
                context.startActivity(i)
                "App de mensagens aberto pra $numero -- revise e envie."
            } catch (e: Exception) {
                "Não consegui abrir o app de mensagens: ${e.message}"
            }
        }
        if (CAMERA.containsMatchIn(t)) {
            return try {
                context.startActivity(
                    Intent(MediaStore.INTENT_ACTION_STILL_IMAGE_CAMERA).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                )
                "Câmera aberta."
            } catch (e: Exception) {
                "Não consegui abrir a câmera: ${e.message}"
            }
        }
        if (CONFIG_WIFI.containsMatchIn(t)) {
            return try {
                // Android proíbe app comum LIGAR/DESLIGAR o Wi-Fi sozinho
                // (desde o 10) -- o painel do sistema é o mais perto do
                // "controla o wifi" possível de forma honesta: abre direto
                // no interruptor, um toque seu resolve.
                val acao = if (Build.VERSION.SDK_INT >= 29) Settings.Panel.ACTION_WIFI else Settings.ACTION_WIFI_SETTINGS
                context.startActivity(Intent(acao).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                "Painel do Wi-Fi aberto -- o Android não deixa um app comum alternar sozinho."
            } catch (e: Exception) {
                "Não consegui abrir as configurações de Wi-Fi: ${e.message}"
            }
        }
        if (CONFIG_BLUETOOTH.containsMatchIn(t)) {
            return try {
                context.startActivity(Intent(Settings.ACTION_BLUETOOTH_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                "Configurações de Bluetooth abertas -- o Android não deixa um app comum alternar sozinho."
            } catch (e: Exception) {
                "Não consegui abrir as configurações de Bluetooth: ${e.message}"
            }
        }
        PESQUISA.find(t)?.let { m ->
            val termo = m.groupValues[1].trim(' ', '.', '!', '?')
            if (termo.isNotEmpty()) {
                return try {
                    val uri = Uri.parse("https://www.google.com/search?q=${Uri.encode(termo)}")
                    context.startActivity(Intent(Intent.ACTION_VIEW, uri).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                    "Pesquisando \"$termo\" no navegador."
                } catch (e: Exception) {
                    "Não consegui abrir o navegador: ${e.message}"
                }
            }
        }

        TOCAR.find(t)?.let { m ->
            return tocarMusica(context, m.groupValues[1])
        }

        if (BATERIA_DETALHE.containsMatchIn(t)) {
            return formatar("bateria_detalhada", DeviceCommands.executar(context, "bateria_detalhada", JSONObject()))
        }
        if (BATERIA.containsMatchIn(t)) {
            return formatar("bateria", DeviceCommands.executar(context, "bateria", JSONObject()))
        }
        if (LANTERNA_ON.containsMatchIn(t)) {
            val p = JSONObject().put("ligar", true)
            return formatar("lanterna_on", DeviceCommands.executar(context, "lanterna", p))
        }
        if (LANTERNA_OFF.containsMatchIn(t)) {
            val p = JSONObject().put("ligar", false)
            return formatar("lanterna_off", DeviceCommands.executar(context, "lanterna", p))
        }
        if (VOLUME_MUTE.containsMatchIn(t)) {
            val p = JSONObject().put("acao", "mutar")
            return formatar("volume", DeviceCommands.executar(context, "volume_celular", p))
        }
        if (VOLUME_UP.containsMatchIn(t)) {
            val p = JSONObject().put("acao", "subir")
            return formatar("volume", DeviceCommands.executar(context, "volume_celular", p))
        }
        if (VOLUME_DOWN.containsMatchIn(t)) {
            val p = JSONObject().put("acao", "descer")
            return formatar("volume", DeviceCommands.executar(context, "volume_celular", p))
        }
        if (DND_ON.containsMatchIn(t)) {
            val p = JSONObject().put("ligar", true)
            return formatar("dnd", DeviceCommands.executar(context, "nao_perturbe", p))
        }
        if (DND_OFF.containsMatchIn(t)) {
            val p = JSONObject().put("ligar", false)
            return formatar("dnd", DeviceCommands.executar(context, "nao_perturbe", p))
        }
        if (MODO_SILENCIOSO.containsMatchIn(t)) {
            return formatar("modo_toque", DeviceCommands.executar(context, "modo_toque", JSONObject().put("modo", "silencioso")))
        }
        if (MODO_VIBRAR.containsMatchIn(t)) {
            return formatar("modo_toque", DeviceCommands.executar(context, "modo_toque", JSONObject().put("modo", "vibrar")))
        }
        if (MODO_NORMAL.containsMatchIn(t)) {
            return formatar("modo_toque", DeviceCommands.executar(context, "modo_toque", JSONObject().put("modo", "normal")))
        }
        BRILHO.find(t)?.let { m ->
            val pct = m.groupValues[1].toIntOrNull() ?: 50
            return formatar("brilho", DeviceCommands.executar(context, "brilho", JSONObject().put("percentual", pct)))
        }
        if (LOCALIZACAO.containsMatchIn(t)) {
            return formatar("localizacao", DeviceCommands.executar(context, "localizacao", JSONObject()))
        }
        if (ARMAZENAMENTO.containsMatchIn(t)) {
            return formatar("armazenamento", DeviceCommands.executar(context, "armazenamento", JSONObject()))
        }
        if (CONSUMO_DADOS.containsMatchIn(t)) {
            return formatar("consumo_dados", DeviceCommands.executar(context, "consumo_dados", JSONObject()))
        }
        if (STATUS_REDE.containsMatchIn(t)) {
            return formatar("status_rede", DeviceCommands.executar(context, "status_rede", JSONObject()))
        }

        // "abrir app" checado por ÚLTIMO -- é o mais genérico (qualquer
        // "abre X" cai aqui se não bateu em nada mais específico antes).
        ABRIR_APP.find(t)?.let { m ->
            val nome = m.groupValues[1].trim(' ', '.', '!', '?')
            if (nome.isNotEmpty()) {
                val r = DeviceCommands.executar(context, "abrir_app", JSONObject().put("nome", nome))
                return if (r.has("erro")) r.getString("erro") else "Abrindo $nome..."
            }
        }

        return null
    }

    /** Formata sem zeros inúteis: 96.0 -> "96", 7.5 -> "7.5". */
    private fun numero(v: Double): String =
        if (v == Math.floor(v) && !v.isInfinite()) v.toLong().toString()
        else String.format(Locale("pt", "BR"), "%.2f", v)

    private fun tocarMusica(context: Context, pedidoBruto: String): String {
        var pedido = pedidoBruto.trim(' ', '.', '!', '?')
        var spotify = false
        SERVICO_SPOTIFY.find(pedido)?.let { m -> spotify = true; pedido = pedido.removeRange(m.range) }
        SERVICO_YOUTUBE.find(pedido)?.let { m -> pedido = pedido.removeRange(m.range) }
        pedido = pedido.trim(' ', ',', '.', '!', '?')
        if (pedido.isEmpty()) return "Tocar qual música?"

        return try {
            if (spotify) {
                val uri = Uri.parse("spotify:search:${Uri.encode(pedido)}")
                context.startActivity(Intent(Intent.ACTION_VIEW, uri).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                "Abri \"$pedido\" no Spotify -- toca na faixa que quiser."
            } else {
                val uri = Uri.parse("https://www.youtube.com/results?search_query=${Uri.encode(pedido)}")
                context.startActivity(Intent(Intent.ACTION_VIEW, uri).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                "Abri \"$pedido\" no YouTube -- toca no primeiro vídeo pra tocar."
            }
        } catch (e: Exception) {
            "Não consegui abrir: ${e.message}"
        }
    }

    /** Traduz o JSON cru de DeviceCommands.executar() numa frase --
     * mesma ideia de plugins/device_control.py, só que local. */
    private fun formatar(tipo: String, r: JSONObject): String {
        if (r.has("erro")) return r.getString("erro")
        return when (tipo) {
            "bateria" -> {
                val status = if (r.optBoolean("carregando")) "carregando" else "na bateria"
                "O celular está com ${r.optInt("nivel")}% de bateria ($status)."
            }
            "bateria_detalhada" -> {
                val partes = mutableListOf("saúde: ${r.optString("saude", "?")}")
                if (r.has("nivel")) partes.add("carga: ${r.optInt("nivel")}%")
                if (r.has("temperatura_c")) partes.add("temperatura: ${r.optDouble("temperatura_c")}°C")
                if (r.has("voltagem_v")) partes.add("voltagem: ${r.optDouble("voltagem_v")}V")
                "Bateria -- " + partes.joinToString(", ") + "."
            }
            "lanterna_on" -> "Lanterna ligada."
            "lanterna_off" -> "Lanterna desligada."
            "volume" -> "Volume ajustado."
            "dnd" -> if (r.optBoolean("nao_perturbe")) "Não Perturbe ligado." else "Não Perturbe desligado."
            "modo_toque" -> "Celular no modo ${r.optString("modo", "normal")}."
            "brilho" -> "Brilho ajustado para ${r.optInt("percentual")}%."
            "localizacao" -> {
                val lat = r.optDouble("latitude")
                val lon = r.optDouble("longitude")
                "Você está por volta de $lat, $lon. Mapa: https://maps.google.com/?q=$lat,$lon"
            }
            "armazenamento" -> "Armazenamento: ${r.optDouble("livre_gb")}GB livres de ${r.optDouble("total_gb")}GB."
            "consumo_dados" -> {
                "Consumo de dados nos últimos ${r.optInt("periodo_dias", 30)} dias: " +
                    "${r.optInt("movel_mb")}MB móveis + ${r.optInt("wifi_mb")}MB Wi-Fi."
            }
            "status_rede" -> {
                val internet = if (r.optBoolean("tem_internet")) "com internet" else "sem internet confirmada"
                "Conectado por ${r.optString("conexao", "?")} ($internet)."
            }
            else -> r.toString()
        }
    }
}
