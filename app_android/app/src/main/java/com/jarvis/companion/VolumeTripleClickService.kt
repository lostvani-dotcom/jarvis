package com.jarvis.companion

import android.accessibilityservice.AccessibilityService
import android.content.Intent
import android.os.SystemClock
import android.view.KeyEvent
import android.view.accessibility.AccessibilityEvent

/** Ativação por hardware: 3 toques seguidos no botão de BAIXAR volume
 * (numa janela curta) abrem o Ultron já ouvindo, sem precisar
 * destravar o celular e tocar no app -- útil com o celular no
 * bolso/mesa. Exige AccessibilityService porque apps comuns não
 * recebem eventos de tecla física do sistema (nem com o app em primeiro
 * plano) -- é o mesmo mecanismo usado por apps de "abrir câmera com
 * volume" -- e precisa ser ativado manualmente pelo usuário em
 * Configurações > Acessibilidade (SettingsActivity guia pra lá).
 *
 * Não lê o conteúdo da tela nem de outros apps: `canRequestFilterKeyEvents`
 * só entrega eventos de TECLA (ver res/xml/accessibility_service_config.xml),
 * o `accessibilityEventTypes="typeAllMask"` é exigido pelo Android pra
 * declarar o serviço, mas `onAccessibilityEvent` fica vazio de propósito. */
class VolumeTripleClickService : AccessibilityService() {

    private var toques = 0
    private var primeiroToqueEm = 0L
    private val janelaMs = 1200L

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        // Intencionalmente vazio -- este serviço só usa onKeyEvent.
    }

    override fun onInterrupt() {}

    override fun onKeyEvent(event: KeyEvent?): Boolean {
        if (event == null || event.keyCode != KeyEvent.KEYCODE_VOLUME_DOWN || event.action != KeyEvent.ACTION_DOWN) {
            return false
        }
        val agora = SystemClock.elapsedRealtime()
        if (agora - primeiroToqueEm > janelaMs) {
            toques = 0
            primeiroToqueEm = agora
        }
        toques++
        if (toques >= 3) {
            toques = 0
            abrirEOuvir()
            return true  // consome o 3º toque -- não deixa o volume abaixar junto
        }
        return false
    }

    private fun abrirEOuvir() {
        val intent = Intent(this, MainActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            putExtra(MainActivity.EXTRA_AUTO_INICIAR_ESCUTA, true)
        }
        startActivity(intent)
    }
}
