package com.jarvis.companion

import android.content.Context
import android.media.MediaRecorder
import android.os.Build
import java.io.File

/** Grava uma amostra da voz do usuário pelo microfone do celular
 * (MPEG-4/AAC, o formato nativo do MediaRecorder do Android) pra
 * mandar pro Ultron do PC treinar a clonagem de voz (ver
 * voz/clonagem.py:salvar_amostra_upload e
 * server/http_server.py:/voz/amostra). Alternativa a gravar pelo
 * microfone do PC (voz/clonagem.py:gravar_amostra) -- mesmo arquivo
 * final, dois jeitos de gerar. */
class VoiceSampleRecorder(private val context: Context) {

    private var recorder: MediaRecorder? = null
    var arquivo: File? = null
        private set

    fun iniciar() {
        val destino = File(context.cacheDir, "amostra_voz_gravada.m4a")
        arquivo = destino

        @Suppress("DEPRECATION")
        val gravador = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            MediaRecorder(context)
        } else {
            MediaRecorder()
        }
        gravador.apply {
            setAudioSource(MediaRecorder.AudioSource.MIC)
            setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            setAudioSamplingRate(44100)
            setAudioEncodingBitRate(128000)
            setOutputFile(destino.absolutePath)
            prepare()
            start()
        }
        recorder = gravador
    }

    /** Para a gravação e devolve o arquivo pronto (ou null se algo deu
     * errado / nunca chegou a iniciar). */
    fun parar(): File? {
        val gravador = recorder ?: return null
        return try {
            gravador.stop()
            arquivo
        } catch (e: Exception) {
            // stop() lança RuntimeException se parou cedo demais (sem
            // áudio nenhum capturado) -- trata como "sem gravação".
            null
        } finally {
            gravador.release()
            recorder = null
        }
    }

    fun cancelar() {
        try {
            recorder?.stop()
        } catch (e: Exception) {
            // melhor-esforço -- só queremos liberar o recurso
        }
        recorder?.release()
        recorder = null
        arquivo?.delete()
    }
}
