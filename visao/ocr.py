"""
visao/ocr.py
==============
Leitura de texto em imagens (OCR) via `pytesseract`, que por sua vez
depende do binário Tesseract instalado no sistema operacional (não é
só `pip install` -- ver requirements-visao.txt para instruções).
"""

import os

from logs.logger import get_logger

log = get_logger("visao")

try:
    import pytesseract
    from PIL import Image
    HAS_OCR_LIBS = True
except ImportError:
    HAS_OCR_LIBS = False


def _localizar_tesseract():
    """O instalador do Tesseract (UB-Mannheim/winget) NÃO adiciona o
    binário ao PATH por padrão, então o pytesseract não o acha e o OCR
    fica "indisponível" mesmo instalado. Aqui a gente procura nos
    caminhos de instalação padrão do Windows e aponta o pytesseract pra
    ele explicitamente -- assim o OCR funciona logo após instalar, sem
    o usuário ter que mexer no PATH manualmente."""
    if not HAS_OCR_LIBS or os.name != "nt":
        return
    candidatos = [
        os.path.expandvars(r"%ProgramFiles%\Tesseract-OCR\tesseract.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Tesseract-OCR\tesseract.exe"),
        os.path.expandvars(r"%LocalAppData%\Programs\Tesseract-OCR\tesseract.exe"),
    ]
    for caminho in candidatos:
        if os.path.isfile(caminho):
            pytesseract.pytesseract.tesseract_cmd = caminho
            return


if HAS_OCR_LIBS:
    _localizar_tesseract()


def available() -> bool:
    if not HAS_OCR_LIBS:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


_idioma_cache = None


def _resolver_idioma(lang: str) -> str:
    """Se o idioma pedido (ex.: 'por') NÃO estiver instalado no Tesseract,
    cai pro 'eng' (que vem por padrão) em vez de falhar e devolver texto
    vazio. O instalador do Tesseract não traz o português por padrão, e
    o OCR em inglês lê texto em português numa boa (mesmo alfabeto) --
    então é melhor ler com 'eng' do que não ler nada. Resultado
    cacheado (consultar os idiomas chama o binário)."""
    global _idioma_cache
    if _idioma_cache is None:
        try:
            _idioma_cache = set(pytesseract.get_languages(config=""))
        except Exception:
            _idioma_cache = set()
    if lang in _idioma_cache:
        return lang
    if "eng" in _idioma_cache:
        return "eng"
    return lang  # deixa o pytesseract reclamar se nem eng existir


def read_text_from_file(path: str, lang: str = "por") -> str:
    if not HAS_OCR_LIBS:
        raise RuntimeError("Instale 'pytesseract' e 'Pillow' (e o binário Tesseract OCR) para OCR.")
    image = Image.open(path)
    return pytesseract.image_to_string(image, lang=_resolver_idioma(lang))


def read_text_from_frame(frame, lang: str = "por") -> str:
    """frame: numpy array BGR (ex.: vindo de visao.camera.Camera.snapshot())."""
    if not HAS_OCR_LIBS:
        raise RuntimeError("Instale 'pytesseract' e 'Pillow' (e o binário Tesseract OCR) para OCR.")
    import cv2
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    image = Image.fromarray(rgb)
    return pytesseract.image_to_string(image, lang=_resolver_idioma(lang))
