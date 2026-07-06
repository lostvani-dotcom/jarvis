package com.jarvis.companion

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import kotlin.random.Random

/**
 * Mostra uma notificação do sistema pra mensagens espontâneas do
 * Jarvis (lembrete, comentário de observação -- ver
 * NotifyListenerService.kt, GET /poll) quando o app não está aberto
 * na tela -- sem isso, não haveria como o usuário saber que o Ultron
 * "falou" algo enquanto o app estava fechado.
 */
object NotificacaoLocal {
    private const val CANAL_ID = "jarvis_mensagens"

    fun mostrar(context: Context, titulo: String, texto: String) {
        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val canal = NotificationChannel(
                CANAL_ID, "Mensagens do Ultron", NotificationManager.IMPORTANCE_DEFAULT,
            )
            nm.createNotificationChannel(canal)
        }

        val abrirAppIntent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pendingIntent = PendingIntent.getActivity(
            context, 0, abrirAppIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        val notificacao = NotificationCompat.Builder(context, CANAL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(titulo)
            .setContentText(texto)
            .setStyle(NotificationCompat.BigTextStyle().bigText(texto))
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .build()

        nm.notify(Random.nextInt(), notificacao)
    }
}
