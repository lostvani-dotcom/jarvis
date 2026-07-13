package com.ultron.redcore

import android.net.Uri
import android.webkit.WebResourceResponse

/** Mesma lista de domínios do bloqueio de anúncios/rastreadores do
 * RedCore do PC (gui/redcore.py:_DOMINIOS_BLOQUEADOS) -- copiada aqui
 * porque cada app Android é um módulo Gradle separado, sem código
 * compartilhado com o Python do PC. Lista curada manualmente (domínio
 * claramente de anúncio/rastreamento/analytics, nunca CDN genérica),
 * pra não arriscar quebrar algum site que precise de um domínio
 * bloqueado por engano. */
object AdBlock {
    private val DOMINIOS_BLOQUEADOS = setOf(
        "doubleclick.net", "googlesyndication.com", "googleadservices.com", "google-analytics.com",
        "googletagmanager.com", "googletagservices.com", "adservice.google.com",
        "adnxs.com", "adsrvr.org", "advertising.com", "taboola.com", "outbrain.com",
        "criteo.com", "criteo.net", "scorecardresearch.com", "quantserve.com", "quantcount.com",
        "moatads.com", "pubmatic.com", "rubiconproject.com", "openx.net", "media.net",
        "amazon-adsystem.com", "adform.net", "adroll.com", "bidswitch.net", "casalemedia.com",
        "contextweb.com", "districtm.io", "gumgum.com", "indexexchange.com", "lijit.com",
        "mathtag.com", "sharethrough.com", "smartadserver.com", "spotxchange.com", "teads.tv",
        "yieldmo.com", "zedo.com", "3lift.com", "adcolony.com", "applovin.com", "chartboost.com",
        "unityads.unity3d.com", "vungle.com", "mgid.com", "propellerads.com", "popads.net",
        "exoclick.com", "trafficjunky.com", "adsterra.com", "bidvertiser.com", "revcontent.com",
        "hotjar.com", "mixpanel.com", "fullstory.com", "mouseflow.com", "crazyegg.com",
        "clicktale.net", "analytics.tiktok.com", "ads-twitter.com",
        "bat.bing.com", "clarity.ms", "adjust.com", "kochava.com", "appsflyer.com",
        "doubleverify.com", "adsafeprotected.com", "serving-sys.com", "2mdn.net",
        "flashtalking.com", "tribalfusion.com", "adblade.com",
    )

    fun bloqueado(url: String): Boolean {
        val host = try {
            Uri.parse(url).host?.lowercase()
        } catch (e: Exception) {
            null
        } ?: return false
        return DOMINIOS_BLOQUEADOS.any { host == it || host.endsWith(".$it") }
    }

    /** shouldInterceptRequest não aceita null pra "bloqueado" (null
     * significa "segue o carregamento normal") -- uma resposta vazia
     * de verdade é o jeito certo de devolver "nada" sem quebrar a
     * página (mesmo efeito de info.block(True) no Qt do RedCore do PC). */
    fun respostaVazia(): WebResourceResponse = WebResourceResponse("text/plain", "utf-8", null)
}
