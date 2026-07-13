package com.jarvis.companion

import android.annotation.TargetApi
import android.app.Activity
import android.app.KeyguardManager
import android.content.Context
import android.content.Intent
import android.hardware.biometrics.BiometricPrompt
import android.os.Build
import android.os.CancellationSignal

/**
 * Bloqueio do app: só o DONO do celular abre o Ultron, usando a face/
 * digital/PIN que já está cadastrada no próprio aparelho.
 *
 * Por que assim, e não uma "câmera vendo a todo momento":
 * - O Android PROÍBE um app comum de acessar a câmera em segundo plano
 *   (desde o Android 9) -- um vigia de câmera sempre ligado simplesmente
 *   não roda. Então "ver a câmera o tempo todo e travar se for outra
 *   pessoa" não é possível pra um app normal.
 * - Reconhecimento facial próprio (comparar rostos) é um modelo de ML
 *   pesado e pouco confiável.
 * - O jeito CERTO e seguro de "só eu uso" é reaproveitar o desbloqueio
 *   biométrico do próprio Android (a face/digital que você cadastrou nas
 *   configurações do celular). É o mesmo mecanismo que protege seu banco:
 *   confiável, testado, e a Google mantém. Se alguém que não é você tentar
 *   abrir o Ultron, esbarra nessa verificação e não passa.
 *
 * Usa SÓ classes do framework (KeyguardManager / BiometricPrompt) -- zero
 * dependência nova no Gradle.
 */
object AppLock {

    private const val REQ_CREDENCIAL = 4711

    fun temBloqueioConfigurado(context: Context): Boolean {
        val km = context.getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager
        return km.isDeviceSecure
    }

    /** Pede a autenticação do dono. Em API 28+ usa o BiometricPrompt
     * (face/digital com a UI bonita do sistema); em 26-27 cai pro
     * KeyguardManager (PIN/padrão/biometria via tela de credencial).
     * `onSucesso`/`onFalha` sempre chamados na thread principal. */
    fun autenticar(activity: Activity, onSucesso: () -> Unit, onFalha: () -> Unit) {
        if (!temBloqueioConfigurado(activity)) {
            // Sem lock no celular não há como verificar o dono -- deixa
            // passar (o setup guia o usuário a cadastrar antes).
            onSucesso()
            return
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            autenticarBiometricPrompt(activity, onSucesso, onFalha)
        } else {
            autenticarKeyguard(activity)
        }
    }

    // Só chamado com SDK_INT >= P (ver autenticar() acima) -- @TargetApi
    // silencia o NewApi do lint sem esconder um guard real que já existe.
    @TargetApi(Build.VERSION_CODES.P)
    private fun autenticarBiometricPrompt(activity: Activity, onSucesso: () -> Unit, onFalha: () -> Unit) {
        @Suppress("DEPRECATION")
        val builder = BiometricPrompt.Builder(activity)
            .setTitle("Ultron bloqueado")
            .setSubtitle("Confirme que é você pra abrir")
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            builder.setDeviceCredentialAllowed(true) // permite cair no PIN se a face falhar
        } else {
            builder.setNegativeButton("Cancelar", activity.mainExecutor) { _, _ -> onFalha() }
        }
        val prompt = builder.build()
        prompt.authenticate(
            CancellationSignal(), activity.mainExecutor,
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult?) {
                    activity.runOnUiThread(onSucesso)
                }
                override fun onAuthenticationError(errorCode: Int, errString: CharSequence?) {
                    activity.runOnUiThread(onFalha)
                }
                // onAuthenticationFailed (tentativa errada) NÃO encerra --
                // o sistema deixa tentar de novo; só erro/cancelamento falha.
            },
        )
    }

    private fun autenticarKeyguard(activity: Activity) {
        val km = activity.getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager
        @Suppress("DEPRECATION")
        val intent = km.createConfirmDeviceCredentialIntent("Ultron bloqueado", "Confirme que é você pra abrir")
        if (intent != null) {
            activity.startActivityForResult(intent, REQ_CREDENCIAL)
        }
    }

    /** Chame do onActivityResult da Activity pra saber o resultado no
     * caminho KeyguardManager (API 26-27). Retorna true se autenticou. */
    fun resultadoKeyguard(requestCode: Int, resultCode: Int): Boolean =
        requestCode == REQ_CREDENCIAL && resultCode == Activity.RESULT_OK

    fun ehRequestKeyguard(requestCode: Int): Boolean = requestCode == REQ_CREDENCIAL
}
