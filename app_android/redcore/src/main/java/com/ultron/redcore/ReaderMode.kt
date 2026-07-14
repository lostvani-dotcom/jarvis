package com.ultron.redcore

/** Modo leitura: mesma heurística do RedCore do PC (gui/redcore.py,
 * `_JS_MODO_LEITURA`) -- esconde clutter comum por seletor de
 * classe/id/tag e recentraliza o texto numa coluna legível. Não é um
 * extrator de conteúdo tipo Readability, só o suficiente pra limpar a
 * maioria dos artigos. Por aba, não persiste entre páginas (ver
 * MainActivity.kt: reseta no onPageStarted). */
object ReaderMode {
    const val JS = """
(function() {
  var id = 'ultron-modo-leitura';
  var existente = document.getElementById(id);
  if (existente) { existente.remove(); return false; }
  var style = document.createElement('style');
  style.id = id;
  style.textContent = `
    nav, header, footer, aside, iframe,
    [class*="sidebar" i], [class*="cookie" i], [class*="popup" i],
    [class*="modal" i], [class*="banner" i], [class*="newsletter" i],
    [class*="subscribe" i], [class*="related" i], [class*="recommend" i],
    [class*="comment" i], [class*="share" i], [class*="social" i],
    [class*="advert" i], [class*=" ad-" i], [class^="ad-" i],
    [id*="sidebar" i], [id*="comment" i], [role="banner"],
    [role="navigation"], [role="complementary"]
      { display: none !important; }
    html, body {
      max-width: 720px !important; margin: 0 auto !important; padding: 24px !important;
      font-family: Georgia, "Times New Roman", serif !important; font-size: 19px !important;
      line-height: 1.7 !important; background: #f7f2e9 !important; color: #222 !important;
    }
    body * { max-width: 100% !important; float: none !important; }
    img, video, figure { height: auto !important; }
  `;
  document.head.appendChild(style);
  return true;
})();
"""
}
