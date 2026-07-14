package com.jarvis.companion

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.widget.RemoteViews
import kotlin.concurrent.thread

/** Widget de tela inicial: status da conexão com o Ultron do PC +
 * atalho de um toque pro microfone (reaproveita EXTRA_AUTO_INICIAR_ESCUTA,
 * mesmo caminho do atalho de hardware -- ver VolumeTripleClickService.kt).
 *
 * Sem processo de fundo dedicado (nada de WorkManager) -- o Android já
 * chama `onUpdate` sozinho a cada `updatePeriodMillis` (30 min, o
 * mínimo que o sistema realmente respeita, mesmo pedindo menos) e toda
 * vez que o widget é adicionado à tela. Entre atualizações, o texto de
 * status fica com a última leitura conhecida (cacheada em Prefs) --
 * "quase ao vivo", não ao vivo de verdade, sem gastar bateria com
 * verificação constante em segundo plano. */
class UltronWidgetProvider : AppWidgetProvider() {

    companion object {
        /** Chamado de qualquer lugar do app que acabou de aprender se o
         * PC está alcançável (ex.: MainActivity depois de checarAtualizacao)
         * -- empurra a atualização pro widget na hora, sem esperar os
         * até 30 minutos do ciclo automático. */
        fun notificarStatus(context: Context, online: Boolean) {
            val prefs = Prefs(context)
            prefs.widgetUltimoStatusOnline = online
            atualizarTodos(context)
        }

        fun atualizarTodos(context: Context) {
            val manager = AppWidgetManager.getInstance(context)
            val ids = manager.getAppWidgetIds(ComponentName(context, UltronWidgetProvider::class.java))
            if (ids.isNotEmpty()) {
                context.sendBroadcast(Intent(context, UltronWidgetProvider::class.java).apply {
                    action = AppWidgetManager.ACTION_APPWIDGET_UPDATE
                    putExtra(AppWidgetManager.EXTRA_APPWIDGET_IDS, ids)
                })
            }
        }
    }

    override fun onUpdate(context: Context, manager: AppWidgetManager, appWidgetIds: IntArray) {
        val prefs = Prefs(context)
        for (id in appWidgetIds) {
            manager.updateAppWidget(id, construirViews(context, prefs))
        }
        // Confere de verdade em segundo plano (não bloqueia onUpdate,
        // que tem uma janela curta antes do Android considerar ANR) --
        // quando terminar, atualiza o widget de novo com o resultado
        // fresco. Sem host/token configurado, nem tenta.
        if (prefs.host.isNotEmpty() && prefs.token.isNotEmpty()) {
            thread {
                val online = JarvisClient.status(prefs.baseUrl)
                prefs.widgetUltimoStatusOnline = online
                for (id in appWidgetIds) {
                    manager.updateAppWidget(id, construirViews(context, prefs))
                }
            }
        }
    }

    private fun construirViews(context: Context, prefs: Prefs): RemoteViews {
        val views = RemoteViews(context.packageName, R.layout.widget_ultron)

        val status = when {
            prefs.host.isEmpty() -> "Não configurado"
            prefs.widgetUltimoStatusOnline == true -> "Conectado ao PC"
            prefs.widgetUltimoStatusOnline == false -> "PC fora de alcance"
            else -> "Verificando..."
        }
        views.setTextViewText(R.id.widgetStatus, status)

        val abrirApp = PendingIntent.getActivity(
            context, 0, Intent(context, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        views.setOnClickPendingIntent(R.id.widgetRoot, abrirApp)

        val abrirEOuvir = PendingIntent.getActivity(
            context, 1,
            Intent(context, MainActivity::class.java).apply {
                putExtra(MainActivity.EXTRA_AUTO_INICIAR_ESCUTA, true)
            },
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        views.setOnClickPendingIntent(R.id.widgetMicButton, abrirEOuvir)

        return views
    }
}
