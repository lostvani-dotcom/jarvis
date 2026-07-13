package com.ultron.loja

import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress

/**
 * Descoberta automática do Ultron na rede local via UDP broadcast --
 * mesmo protocolo do app Companion (app_android/app/.../Discovery.kt)
 * e de server/discovery.py. A Loja só precisa do IP/porta -- os
 * endpoints que ela usa (/loja/catalogo, /loja/apps/<arquivo>) não
 * exigem token (ver server/http_server.py), então o token da resposta
 * é ignorado aqui de propósito.
 */
object Discovery {
    private const val MAGIC = "JARVIS_DISCOVER"
    private const val PORTA_DESCOBERTA = 8766

    data class Resultado(val ip: String, val porta: Int)

    /** Bloqueia até achar o servidor ou estourar o timeout -- chame
     * numa thread de fundo, nunca na thread principal. */
    fun buscar(timeoutMs: Int = 3000): Resultado? {
        var socket: DatagramSocket? = null
        return try {
            socket = DatagramSocket().apply {
                broadcast = true
                soTimeout = timeoutMs
            }

            val envio = MAGIC.toByteArray(Charsets.UTF_8)
            socket.send(
                DatagramPacket(envio, envio.size, InetAddress.getByName("255.255.255.255"), PORTA_DESCOBERTA),
            )

            val buffer = ByteArray(1024)
            val recebido = DatagramPacket(buffer, buffer.size)
            socket.receive(recebido)

            val texto = String(recebido.data, 0, recebido.length, Charsets.UTF_8)
            val json = JSONObject(texto)
            val ip = recebido.address?.hostAddress ?: return null
            Resultado(ip, json.optInt("porta_http", 8765))
        } catch (e: Exception) {
            null
        } finally {
            socket?.close()
        }
    }
}
