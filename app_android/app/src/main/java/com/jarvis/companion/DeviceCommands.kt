package com.jarvis.companion

import android.Manifest
import android.app.AppOpsManager
import android.app.NotificationManager
import android.app.usage.NetworkStatsManager
import android.app.usage.UsageStatsManager
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.location.LocationManager
import android.media.AudioAttributes
import android.media.AudioManager
import android.media.RingtoneManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.BatteryManager
import android.os.Build
import android.os.Environment
import android.os.Process
import android.os.StatFs
import android.os.VibrationEffect
import android.os.Vibrator
import android.provider.Settings
import androidx.core.content.ContextCompat
import org.json.JSONObject
import kotlin.concurrent.thread

/**
 * Executa localmente os comandos que o Ultron pede pelo canal HTTP
 * (ver automacao/phone_commands.py, server/http_server.py) -- bateria,
 * abrir um app, app em primeiro plano, volume, lanterna, achar o
 * celular, armazenamento. Chamado pelo loop de polling em
 * NotifyListenerService (roda em segundo plano, com o app fechado).
 */
object DeviceCommands {

    private val ALIASES = mapOf(
        "whatsapp" to "com.whatsapp",
        "instagram" to "com.instagram.android",
        "youtube" to "com.google.android.youtube",
        "chrome" to "com.android.chrome",
        "spotify" to "com.spotify.music",
        "gmail" to "com.google.android.gm",
        "telegram" to "org.telegram.messenger",
        "facebook" to "com.facebook.katana",
        "tiktok" to "com.zhiliaoapp.musically",
        "twitter" to "com.twitter.android",
        "x" to "com.twitter.android",
    )

    fun executar(context: Context, tipo: String, params: JSONObject): JSONObject = try {
        when (tipo) {
            "bateria" -> bateria(context)
            "bateria_detalhada" -> bateriaDetalhada(context)
            "abrir_app" -> abrirApp(context, params.optString("nome", ""))
            "primeiro_plano" -> primeiroPlano(context)
            "volume_celular" -> volumeCelular(context, params.optString("acao", "subir"))
            "lanterna" -> lanterna(context, params.optBoolean("ligar", true))
            "achar_celular" -> acharCelular(context)
            "armazenamento" -> armazenamento()
            "nao_perturbe" -> naoPerturbe(context, params.optBoolean("ligar", true))
            "modo_toque" -> modoToque(context, params.optString("modo", "normal"))
            "brilho" -> brilho(context, params.optInt("percentual", 50))
            "timeout_tela" -> timeoutTela(context, params.optInt("segundos", 60))
            "localizacao" -> localizacao(context)
            "consumo_dados" -> consumoDados(context)
            "status_rede" -> statusRede(context)
            else -> JSONObject().put("erro", "comando desconhecido: $tipo")
        }
    } catch (e: Exception) {
        JSONObject().put("erro", "falha ao executar '$tipo': ${e.message}")
    }

    private fun bateria(context: Context): JSONObject {
        val bm = context.getSystemService(Context.BATTERY_SERVICE) as BatteryManager
        val nivel = bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
        return JSONObject().put("nivel", nivel).put("carregando", bm.isCharging)
    }

    private fun abrirApp(context: Context, nome: String): JSONObject {
        val alvo = nome.trim().lowercase()
        if (alvo.isEmpty()) return JSONObject().put("erro", "não me disseram o nome do app")

        val pm = context.packageManager
        var pacote = ALIASES[alvo]

        if (pacote == null) {
            pacote = pm.getInstalledApplications(0).firstOrNull { app ->
                val label = pm.getApplicationLabel(app).toString().lowercase()
                label.contains(alvo) || app.packageName.lowercase().contains(alvo)
            }?.packageName
        }

        if (pacote == null) {
            return JSONObject().put("erro", "não encontrei nenhum app instalado parecido com \"$nome\"")
        }

        val intent = pm.getLaunchIntentForPackage(pacote)
            ?: return JSONObject().put("erro", "\"$pacote\" não tem uma tela pra abrir")
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(intent)
        return JSONObject().put("pacote", pacote)
    }

    private fun temPermissaoDeUso(context: Context): Boolean {
        val appOps = context.getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
        val modo = appOps.checkOpNoThrow(
            AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), context.packageName,
        )
        return modo == AppOpsManager.MODE_ALLOWED
    }

    private fun primeiroPlano(context: Context): JSONObject {
        if (!temPermissaoDeUso(context)) {
            return JSONObject().put(
                "erro",
                "preciso da permissão \"Acesso ao uso\" pra ver isso -- toque no botão " +
                    "\"Acesso ao uso\" no app e habilite pro Ultron.",
            )
        }

        val usm = context.getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager
        val fim = System.currentTimeMillis()
        val stats = usm.queryUsageStats(UsageStatsManager.INTERVAL_BEST, fim - 60_000, fim)
        val ultimo = stats?.filter { it.lastTimeUsed > 0 }?.maxByOrNull { it.lastTimeUsed }
            ?: return JSONObject().put("erro", "não consegui identificar o app em uso agora")

        val label = try {
            val pm = context.packageManager
            pm.getApplicationLabel(pm.getApplicationInfo(ultimo.packageName, 0)).toString()
        } catch (e: Exception) {
            ultimo.packageName
        }
        return JSONObject().put("app", label).put("pacote", ultimo.packageName)
    }

    private fun volumeCelular(context: Context, acao: String): JSONObject {
        val am = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        val direcao = when (acao) {
            "subir" -> AudioManager.ADJUST_RAISE
            "descer" -> AudioManager.ADJUST_LOWER
            "mutar" -> AudioManager.ADJUST_TOGGLE_MUTE
            else -> AudioManager.ADJUST_RAISE
        }
        am.adjustStreamVolume(AudioManager.STREAM_MUSIC, direcao, AudioManager.FLAG_SHOW_UI)
        return JSONObject().put("ok", true)
    }

    private fun lanterna(context: Context, ligar: Boolean): JSONObject {
        val cm = context.getSystemService(Context.CAMERA_SERVICE) as CameraManager
        val cameraId = cm.cameraIdList.firstOrNull { id ->
            cm.getCameraCharacteristics(id).get(CameraCharacteristics.FLASH_INFO_AVAILABLE) == true
        } ?: return JSONObject().put("erro", "esse celular não tem lanterna/flash detectável")
        cm.setTorchMode(cameraId, ligar)
        return JSONObject().put("ok", true)
    }

    /** Toca um alarme bem alto (mesmo se o celular estiver no
     * silencioso) e vibra por alguns segundos, pra ajudar a achar o
     * aparelho perdido em casa. Roda em thread separada e devolve o
     * "ok" na hora -- o som/vibração continuam por conta própria. */
    private fun acharCelular(context: Context): JSONObject {
        thread {
            var am: AudioManager? = null
            var volumeOriginal = 0
            try {
                am = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
                volumeOriginal = am.getStreamVolume(AudioManager.STREAM_ALARM)
                am.setStreamVolume(AudioManager.STREAM_ALARM, am.getStreamMaxVolume(AudioManager.STREAM_ALARM), 0)

                val ringtone = RingtoneManager.getRingtone(context, RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM))
                ringtone.audioAttributes = AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ALARM).build()
                ringtone.play()

                val vibrator = context.getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
                val padrao = longArrayOf(0, 500, 300, 500, 300, 500)
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    vibrator.vibrate(VibrationEffect.createWaveform(padrao, 0))
                } else {
                    @Suppress("DEPRECATION")
                    vibrator.vibrate(padrao, 0)
                }

                Thread.sleep(8000)
                ringtone.stop()
                vibrator.cancel()
            } catch (e: Exception) {
                // melhor-esforço
            } finally {
                try {
                    am?.setStreamVolume(AudioManager.STREAM_ALARM, volumeOriginal, 0)
                } catch (e: Exception) {
                    // melhor-esforço
                }
            }
        }
        return JSONObject().put("ok", true)
    }

    private fun armazenamento(): JSONObject {
        val stat = StatFs(Environment.getDataDirectory().path)
        val gb = 1024.0 * 1024.0 * 1024.0
        val totalGb = stat.totalBytes / gb
        val livreGb = stat.availableBytes / gb
        return JSONObject()
            .put("total_gb", Math.round(totalGb * 10) / 10.0)
            .put("livre_gb", Math.round(livreGb * 10) / 10.0)
    }

    /** Saúde/temperatura/voltagem/tecnologia da bateria, lidos do intent
     * "sticky" ACTION_BATTERY_CHANGED (não precisa de permissão nova). */
    private fun bateriaDetalhada(context: Context): JSONObject {
        val intent = context.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
            ?: return JSONObject().put("erro", "não consegui ler o estado da bateria agora")
        val temp = intent.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, -1)
        val volt = intent.getIntExtra(BatteryManager.EXTRA_VOLTAGE, -1)
        val nivel = intent.getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
        val escala = intent.getIntExtra(BatteryManager.EXTRA_SCALE, -1)
        val tecnologia = intent.getStringExtra(BatteryManager.EXTRA_TECHNOLOGY) ?: "?"
        val saudeCodigo = intent.getIntExtra(BatteryManager.EXTRA_HEALTH, -1)
        val saude = when (saudeCodigo) {
            BatteryManager.BATTERY_HEALTH_GOOD -> "boa"
            BatteryManager.BATTERY_HEALTH_OVERHEAT -> "superaquecendo"
            BatteryManager.BATTERY_HEALTH_DEAD -> "gasta"
            BatteryManager.BATTERY_HEALTH_OVER_VOLTAGE -> "sobretensão"
            BatteryManager.BATTERY_HEALTH_COLD -> "fria"
            else -> "desconhecida"
        }
        val out = JSONObject()
            .put("saude", saude)
            .put("tecnologia", tecnologia)
        if (temp > 0) out.put("temperatura_c", Math.round(temp / 10.0 * 10) / 10.0)
        if (volt > 0) out.put("voltagem_v", Math.round(volt / 1000.0 * 100) / 100.0)
        if (nivel >= 0 && escala > 0) out.put("nivel", Math.round(nivel * 100.0 / escala))
        return out
    }

    /** Não Perturbe (silêncio total). Precisa do acesso "Não Perturbe"
     * (ACCESS_NOTIFICATION_POLICY), concedido numa tela do Android. */
    private fun naoPerturbe(context: Context, ligar: Boolean): JSONObject {
        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (!nm.isNotificationPolicyAccessGranted) {
            return JSONObject().put(
                "erro",
                "preciso do acesso \"Não Perturbe\" pro Ultron (Configurações do celular > " +
                    "Apps > Acesso especial > Não Perturbe).",
            )
        }
        nm.setInterruptionFilter(
            if (ligar) NotificationManager.INTERRUPTION_FILTER_NONE
            else NotificationManager.INTERRUPTION_FILTER_ALL,
        )
        return JSONObject().put("ok", true).put("nao_perturbe", ligar)
    }

    /** Modo de toque: normal / vibrar / silencioso. O silencioso pode
     * exigir o acesso Não Perturbe em versões novas do Android. */
    private fun modoToque(context: Context, modo: String): JSONObject {
        val am = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        am.ringerMode = when (modo) {
            "vibrar" -> AudioManager.RINGER_MODE_VIBRATE
            "silencioso" -> AudioManager.RINGER_MODE_SILENT
            else -> AudioManager.RINGER_MODE_NORMAL
        }
        return JSONObject().put("ok", true).put("modo", modo)
    }

    /** Brilho da tela (0 a 100%). Precisa da permissão "Modificar
     * configurações do sistema" (WRITE_SETTINGS), concedida numa tela
     * do Android. Coloca o brilho em modo MANUAL primeiro. */
    private fun brilho(context: Context, percentual: Int): JSONObject {
        if (!Settings.System.canWrite(context)) {
            return JSONObject().put(
                "erro",
                "preciso da permissão \"Modificar configurações do sistema\" pro Ultron " +
                    "(Configurações > Apps > Acesso especial).",
            )
        }
        val pct = percentual.coerceIn(0, 100)
        val valor = Math.round(pct / 100.0 * 255).toInt().coerceIn(1, 255)
        Settings.System.putInt(
            context.contentResolver,
            Settings.System.SCREEN_BRIGHTNESS_MODE,
            Settings.System.SCREEN_BRIGHTNESS_MODE_MANUAL,
        )
        Settings.System.putInt(context.contentResolver, Settings.System.SCREEN_BRIGHTNESS, valor)
        return JSONObject().put("ok", true).put("percentual", pct)
    }

    /** Tempo até a tela apagar sozinha, em segundos. Precisa de WRITE_SETTINGS. */
    private fun timeoutTela(context: Context, segundos: Int): JSONObject {
        if (!Settings.System.canWrite(context)) {
            return JSONObject().put("erro", "preciso da permissão \"Modificar configurações do sistema\".")
        }
        val ms = segundos.coerceIn(5, 1800) * 1000
        Settings.System.putInt(context.contentResolver, Settings.System.SCREEN_OFF_TIMEOUT, ms)
        return JSONObject().put("ok", true).put("segundos", segundos)
    }

    /** Última localização conhecida (lat/lon). Precisa de ACCESS_FINE_LOCATION. */
    private fun localizacao(context: Context): JSONObject {
        val temPermissao = ContextCompat.checkSelfPermission(
            context, Manifest.permission.ACCESS_FINE_LOCATION,
        ) == PackageManager.PERMISSION_GRANTED
        if (!temPermissao) {
            return JSONObject().put("erro", "preciso da permissão de localização pro Ultron.")
        }
        val lm = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
        val provedores = listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER)
        var melhor: android.location.Location? = null
        for (p in provedores) {
            try {
                val loc = lm.getLastKnownLocation(p) ?: continue
                if (melhor == null || loc.time > melhor!!.time) melhor = loc
            } catch (e: SecurityException) {
                // sem permissão pra esse provedor -- ignora
            }
        }
        return melhor?.let {
            JSONObject()
                .put("latitude", it.latitude)
                .put("longitude", it.longitude)
                .put("precisao_m", Math.round(it.accuracy.toDouble()))
        } ?: JSONObject().put("erro", "sem localização conhecida ainda (abra um mapa uma vez e tente de novo)")
    }

    /** Consumo total de dados (móvel + Wi-Fi) nos últimos ~30 dias, em MB.
     * Usa o mesmo acesso ao uso (PACKAGE_USAGE_STATS) do primeiro_plano. */
    private fun consumoDados(context: Context): JSONObject {
        if (!temPermissaoDeUso(context)) {
            return JSONObject().put(
                "erro",
                "preciso da permissão \"Acesso ao uso\" pra ver o consumo de dados.",
            )
        }
        val nsm = context.getSystemService(Context.NETWORK_STATS_SERVICE) as NetworkStatsManager
        val fim = System.currentTimeMillis()
        val inicio = fim - 30L * 24 * 60 * 60 * 1000
        val mb = 1024.0 * 1024.0
        fun total(tipo: Int): Double = try {
            val b = nsm.querySummaryForDevice(tipo, null, inicio, fim)
            (b.rxBytes + b.txBytes) / mb
        } catch (e: Exception) {
            0.0
        }
        val movel = total(ConnectivityManager.TYPE_MOBILE)
        val wifi = total(ConnectivityManager.TYPE_WIFI)
        return JSONObject()
            .put("movel_mb", Math.round(movel))
            .put("wifi_mb", Math.round(wifi))
            .put("periodo_dias", 30)
    }

    /** Como o celular está conectado agora (Wi-Fi / dados móveis / nenhum). */
    private fun statusRede(context: Context): JSONObject {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val rede = cm.activeNetwork ?: return JSONObject().put("conexao", "nenhuma")
        val caps = cm.getNetworkCapabilities(rede) ?: return JSONObject().put("conexao", "nenhuma")
        val tipo = when {
            caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "wifi"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "dados moveis"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> "ethernet"
            else -> "outra"
        }
        return JSONObject()
            .put("conexao", tipo)
            .put("tem_internet", caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED))
    }
}
