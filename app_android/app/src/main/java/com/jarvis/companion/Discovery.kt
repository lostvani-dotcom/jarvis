package com.jarvis.companion

import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress

/**
 * Descoberta automática do Ultron na rede local via UDP broadcast --
 * ver server/discovery.py. Manda "JARVIS_DISCOVER" pra
 * 255.255.255.255:8766 e espera uma resposta JSON com o IP (endereço
 * de origem do pacote), a porta HTTP e o TOKEN do servidor -- decisão
 * consciente pra permitir conexão totalmente automática, sem digitar
 * nada (ver docstring de server/discovery.py sobre a troca de
 * segurança envolvida: o perímetro de confiança passa a ser "estar na
 * mesma Wi-Fi", não mais "conhecer o token").
 */
object Discovery {
    private const val MAGIC = "JARVIS_DISCOVER"
    private const val PORTA_DESCOBERTA = 8766

    data class Resultado(val ip: String, val porta: Int, val token: String)

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
            val token = json.optString("token", "")
            if (token.isEmpty()) return null
            Resultado(ip, json.optInt("porta_http", 8765), token)
        } catch (e: Exception) {
            null
        } finally {
            socket?.close()
        }
    }
}
