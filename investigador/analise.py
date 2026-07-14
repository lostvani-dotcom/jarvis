"""
investigador/analise.py
==========================
"Investigador Universal": dado um arquivo (EXE, APK, PDF, imagem,
vídeo) ou uma URL, tenta identificar tecnologias/arquitetura/
bibliotecas usadas e sinaliza pontos de atenção.

Análise ESTÁTICA e PASSIVA por design:
  - Arquivos locais: só LÊ bytes/metadados -- nunca executa o arquivo
    analisado (rodar um .exe/.apk desconhecido pra "ver o que faz"
    seria perigoso de verdade, e não é isso que este módulo faz).
  - Sites: UM request HTTP de leitura (cabeçalhos + HTML da página
    pedida) -- nunca varredura ativa (sem fuzzing de parâmetro, sem
    tentar SQLi/XSS, sem varrer portas). Varredura ativa contra um site
    que não é seu, sem autorização, é o tipo de coisa que este projeto
    recusa por padrão (ver plugins/security_scan.py se existir um
    equivalente autorizado de pentest -- aqui é só reconhecimento
    passivo de tecnologia, não teste de invasão).

Limitação honesta: isso é reconhecimento por assinatura/heurística
(extensão, magic bytes, strings legíveis, imports, cabeçalhos HTTP) --
NÃO é engenharia reversa de verdade (sem desmontagem/decompilação) e
NÃO é um scanner de vulnerabilidades real (sem consulta a base de CVE,
sem fuzzing, sem exploração). Serve pra um retrato rápido de "o que é
isso e com o que foi feito", não um laudo de segurança completo --
todo resultado inclui os "indicios" encontrados, nunca uma alegação
de certeza absoluta.
"""

import os
import re
import zipfile

from logs.logger import get_logger

log = get_logger("investigador")

try:
    import pefile
    HAS_PEFILE = True
except ImportError:
    HAS_PEFILE = False

try:
    from pypdf import PdfReader
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

try:
    from PIL import Image, ExifTags
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

_EXT_IMAGEM = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"}
_EXT_VIDEO = {".mp4", ".mkv", ".avi", ".mov", ".webm"}

# Strings legíveis dentro de um EXE que costumam denunciar a tecnologia
# usada -- heurística simples (equivalente ao comando `strings` + grep
# por marcador conhecido), não é análise binária de verdade.
_MARCADORES_EXE = {
    "pyinstaller": "PyInstaller (aplicativo Python empacotado)",
    "python3": "Python (runtime embutido)",
    "electron.exe": "Electron (app desktop com Chromium+Node.js)",
    "node.exe": "Node.js embutido",
    "mscoree.dll": ".NET (CLR da Microsoft)",
    "qt5core.dll": "Qt5 (framework de UI C++)",
    "qt6core.dll": "Qt6 (framework de UI C++)",
    "unityplayer.dll": "Unity (engine de jogos)",
    "unreal": "Unreal Engine",
    "chromiumembedded": "CEF -- Chromium Embedded Framework",
    "libcef.dll": "CEF -- Chromium Embedded Framework",
    "java.exe": "Java (runtime embutido/launcher)",
    "vcruntime": "Visual C++ Runtime (compilado em C/C++)",
    "golang": "Go (build id presente)",
}


def _extensao(caminho: str) -> str:
    return os.path.splitext(caminho)[1].lower()


def _eh_url(alvo: str) -> bool:
    return alvo.lower().startswith("http://") or alvo.lower().startswith("https://")


def _tamanho_legivel(bytes_: int) -> str:
    for unidade in ("B", "KB", "MB", "GB"):
        if bytes_ < 1024:
            return f"{bytes_:.1f}{unidade}"
        bytes_ /= 1024
    return f"{bytes_:.1f}TB"


def _strings_legiveis(dados: bytes, tamanho_minimo: int = 5) -> list:
    """Extrai substrings ASCII imprimíveis -- equivalente simples ao
    utilitário `strings` do Unix, usado só pra procurar marcadores de
    tecnologia conhecidos, não pra dump completo (dump completo de um
    binário grande não cabe numa resposta de chat)."""
    padrao = re.compile(rb"[\x20-\x7e]{%d,}" % tamanho_minimo)
    return [m.decode("ascii", errors="ignore") for m in padrao.findall(dados)]


def _analisar_exe(caminho: str) -> dict:
    with open(caminho, "rb") as f:
        dados = f.read()

    resultado = {
        "tipo": "executável (PE)",
        "tamanho": _tamanho_legivel(len(dados)),
        "indicios_tecnologia": [],
        "detalhes": {},
        "limitacoes": [],
    }

    if dados[:2] != b"MZ":
        resultado["limitacoes"].append("O arquivo não começa com a assinatura MZ esperada de um PE do Windows.")

    strings = _strings_legiveis(dados)
    texto_busca = "\n".join(strings).lower()
    for marcador, explicacao in _MARCADORES_EXE.items():
        if marcador in texto_busca:
            resultado["indicios_tecnologia"].append(explicacao)

    if HAS_PEFILE:
        pe = None
        try:
            pe = pefile.PE(caminho, fast_load=True)
            pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
            resultado["detalhes"]["arquitetura"] = pefile.MACHINE_TYPE.get(pe.FILE_HEADER.Machine, str(pe.FILE_HEADER.Machine))
            dlls_importadas = []
            if hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
                dlls_importadas = [entry.dll.decode(errors="ignore") for entry in pe.DIRECTORY_ENTRY_IMPORT]
            resultado["detalhes"]["dlls_importadas"] = dlls_importadas[:30]
        except Exception as e:
            resultado["limitacoes"].append(f"pefile não conseguiu processar o cabeçalho PE ({e}).")
        finally:
            # pe.close() só rodava no fim feliz do try -- um PE malformado (o
            # tipo de arquivo que este módulo mais existe pra analisar) que
            # falha no meio do parse deixava o mmap do arquivo aberto pra
            # sempre, travando o arquivo (achado real: ficava impossível
            # apagar/mover o arquivo analisado depois, no Windows).
            if pe is not None:
                pe.close()
    else:
        resultado["limitacoes"].append(
            "Instale 'pefile' (requirements-investigador.txt) pra ver arquitetura/DLLs importadas."
        )

    if not resultado["indicios_tecnologia"]:
        resultado["indicios_tecnologia"].append("nenhum marcador de tecnologia conhecido encontrado nas strings legíveis")

    resultado["limitacoes"].append(
        "Isso é reconhecimento por assinatura, não engenharia reversa -- não desmonta nem executa o binário."
    )
    return resultado


_MARCADORES_APK = {
    "libflutter.so": "Flutter",
    "flutter_assets/": "Flutter",
    "libreactnativejni.so": "React Native",
    "index.android.bundle": "React Native",
    "assets/www/cordova.js": "Cordova (WebView híbrido)",
    "assets/www/": "app híbrido baseado em WebView (Cordova/Capacitor ou similar)",
    "classes.dex": "Java/Kotlin nativo (Android SDK)",
    "kotlin/": "Kotlin",
}


def _analisar_apk(caminho: str) -> dict:
    resultado = {
        "tipo": "APK (Android)",
        "tamanho": _tamanho_legivel(os.path.getsize(caminho)),
        "indicios_tecnologia": [],
        "detalhes": {},
        "limitacoes": [],
    }
    try:
        with zipfile.ZipFile(caminho) as z:
            nomes = z.namelist()
    except zipfile.BadZipFile:
        resultado["limitacoes"].append("O arquivo não é um .zip/.apk válido (ou está corrompido).")
        return resultado

    arquiteturas = sorted({n.split("/")[1] for n in nomes if n.startswith("lib/") and "/" in n[4:]})
    if arquiteturas:
        resultado["detalhes"]["arquiteturas_nativas"] = arquiteturas

    assinado = any(n.startswith("META-INF/") and (n.endswith(".RSA") or n.endswith(".DSA") or n.endswith(".EC")) for n in nomes)
    resultado["detalhes"]["assinado"] = assinado

    for marcador, tecnologia in _MARCADORES_APK.items():
        if any(marcador in n for n in nomes) and tecnologia not in resultado["indicios_tecnologia"]:
            resultado["indicios_tecnologia"].append(tecnologia)

    if not resultado["indicios_tecnologia"]:
        resultado["indicios_tecnologia"].append("nenhum marcador de framework conhecido encontrado na estrutura do APK")

    resultado["limitacoes"].append(
        "AndroidManifest.xml está em formato binário -- sem 'aapt'/androguard instalado, não lemos "
        "permissões declaradas nem versão/nome do pacote diretamente daqui."
    )
    return resultado


def _analisar_pdf(caminho: str) -> dict:
    resultado = {
        "tipo": "PDF",
        "tamanho": _tamanho_legivel(os.path.getsize(caminho)),
        "indicios_tecnologia": [],
        "detalhes": {},
        "limitacoes": [],
    }
    if HAS_PYPDF:
        try:
            leitor = PdfReader(caminho)
            metadados = leitor.metadata or {}
            if metadados.get("/Producer"):
                resultado["detalhes"]["producer"] = str(metadados["/Producer"])
            if metadados.get("/Creator"):
                resultado["detalhes"]["creator"] = str(metadados["/Creator"])
            resultado["detalhes"]["paginas"] = len(leitor.pages)
        except Exception as e:
            resultado["limitacoes"].append(f"pypdf não conseguiu ler os metadados ({e}).")
    else:
        resultado["limitacoes"].append("Instale 'pypdf' (requirements-investigador.txt) pra ler metadados/nº de páginas.")

    with open(caminho, "rb") as f:
        dados = f.read()
    if b"/JavaScript" in dados or b"/JS" in dados:
        resultado["indicios_tecnologia"].append("contém JavaScript embutido -- revise antes de abrir com JS habilitado")
    if b"/EmbeddedFile" in dados:
        resultado["indicios_tecnologia"].append("contém arquivo(s) embutido(s) dentro do PDF")
    if b"/OpenAction" in dados or b"/AA" in dados:
        resultado["indicios_tecnologia"].append("possui ação automática configurada para rodar ao abrir")
    if not resultado["indicios_tecnologia"]:
        resultado["indicios_tecnologia"].append("nenhum indício de conteúdo ativo (JS/ação automática/anexo) encontrado")

    resultado["limitacoes"].append("Detecção de JS/anexo é busca por assinatura nos bytes crus, não parsing completo do PDF.")
    return resultado


def _analisar_imagem(caminho: str) -> dict:
    resultado = {
        "tipo": "imagem",
        "tamanho": _tamanho_legivel(os.path.getsize(caminho)),
        "indicios_tecnologia": [],
        "detalhes": {},
        "limitacoes": [],
    }
    if not HAS_PIL:
        resultado["limitacoes"].append("Instale 'Pillow' (requirements-visao.txt) pra ler formato/resolução/EXIF.")
        return resultado
    try:
        with Image.open(caminho) as img:
            resultado["detalhes"]["formato"] = img.format
            resultado["detalhes"]["resolucao"] = f"{img.width}x{img.height}"
            exif_bruto = img._getexif() if hasattr(img, "_getexif") else None
            if exif_bruto:
                tags = {ExifTags.TAGS.get(k, k): v for k, v in exif_bruto.items()}
                if tags.get("Make") or tags.get("Model"):
                    resultado["detalhes"]["camera"] = f"{tags.get('Make', '')} {tags.get('Model', '')}".strip()
                if tags.get("Software"):
                    resultado["detalhes"]["software"] = str(tags["Software"])
                if tags.get("GPSInfo"):
                    resultado["indicios_tecnologia"].append(
                        "contém dados de localização GPS no EXIF -- cuidado antes de compartilhar"
                    )
    except Exception as e:
        resultado["limitacoes"].append(f"Pillow não conseguiu processar a imagem ({e}).")
    if not resultado["indicios_tecnologia"]:
        resultado["indicios_tecnologia"].append("nenhum dado sensível óbvio encontrado no EXIF")
    return resultado


def _analisar_video(caminho: str) -> dict:
    resultado = {
        "tipo": "vídeo",
        "tamanho": _tamanho_legivel(os.path.getsize(caminho)),
        "indicios_tecnologia": [],
        "detalhes": {},
        "limitacoes": [],
    }
    import subprocess
    import shutil as _shutil
    import json as _json

    if not _shutil.which("ffprobe"):
        resultado["limitacoes"].append(
            "Instale o 'ffprobe' (parte do ffmpeg, não é um pacote Python) pra ler codec/resolução/duração."
        )
        return resultado
    try:
        saida = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", caminho],
            capture_output=True, text=True, timeout=15,
        )
        info = _json.loads(saida.stdout or "{}")
        for stream in info.get("streams", []):
            if stream.get("codec_type") == "video":
                resultado["detalhes"]["codec_video"] = stream.get("codec_name")
                resultado["detalhes"]["resolucao"] = f"{stream.get('width')}x{stream.get('height')}"
            if stream.get("codec_type") == "audio":
                resultado["detalhes"]["codec_audio"] = stream.get("codec_name")
        if info.get("format", {}).get("duration"):
            resultado["detalhes"]["duracao_segundos"] = round(float(info["format"]["duration"]), 1)
    except Exception as e:
        resultado["limitacoes"].append(f"ffprobe falhou ao processar o vídeo ({e}).")
    return resultado


_FINGERPRINTS_SITE = {
    "wp-content/": "WordPress",
    "wp-json": "WordPress (REST API)",
    "cdn.shopify.com": "Shopify",
    "__next_data__": "Next.js (React)",
    "_nuxt/": "Nuxt.js (Vue)",
    "django": "Django (indício em cookie/erro)",
    "laravel_session": "Laravel (PHP)",
    "x-drupal-cache": "Drupal",
}
_HEADERS_SEGURANCA = ("content-security-policy", "x-frame-options", "strict-transport-security")


def _analisar_site(url: str) -> dict:
    import urllib.request

    resultado = {
        "tipo": "site",
        "indicios_tecnologia": [],
        "detalhes": {},
        "limitacoes": [
            "Análise passiva: um único GET nessa URL, sem varredura ativa de "
            "portas/parâmetros/injeção -- não é um teste de invasão.",
        ],
    }
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (UltronInvestigador)"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            corpo = resp.read(200_000).decode("utf-8", errors="ignore")
            headers = {k.lower(): v for k, v in resp.getheaders()}
    except Exception as e:
        resultado["limitacoes"].append(f"Não consegui acessar a URL ({e}).")
        return resultado

    if headers.get("server"):
        resultado["detalhes"]["servidor"] = headers["server"]
    if headers.get("x-powered-by"):
        resultado["detalhes"]["x_powered_by"] = headers["x-powered-by"]

    texto_busca = (corpo + " " + " ".join(headers.values())).lower()
    for marcador, tecnologia in _FINGERPRINTS_SITE.items():
        if marcador in texto_busca:
            resultado["indicios_tecnologia"].append(tecnologia)

    m = re.search(r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']([^"\']+)["\']', corpo, re.IGNORECASE)
    if m:
        resultado["detalhes"]["meta_generator"] = m.group(1)

    faltando = [h for h in _HEADERS_SEGURANCA if h not in headers]
    if faltando:
        resultado["indicios_tecnologia"].append(
            f"cabeçalhos de segurança ausentes: {', '.join(faltando)} (possível ponto de atenção, não confirma vulnerabilidade)"
        )
    if not resultado["indicios_tecnologia"]:
        resultado["indicios_tecnologia"].append("nenhum framework/CMS conhecido identificado por fingerprint")

    return resultado


def analisar(alvo: str) -> dict:
    """Ponto de entrada único: recebe um caminho de arquivo local ou
    uma URL, detecta o tipo e despacha pra análise específica. Levanta
    FileNotFoundError se um caminho local não existir."""
    if _eh_url(alvo):
        return _analisar_site(alvo)

    if not os.path.isfile(alvo):
        raise FileNotFoundError(f"Não encontrei o arquivo '{alvo}'.")

    ext = _extensao(alvo)
    if ext in (".exe", ".dll"):
        return _analisar_exe(alvo)
    if ext == ".apk":
        return _analisar_apk(alvo)
    if ext == ".pdf":
        return _analisar_pdf(alvo)
    if ext in _EXT_IMAGEM:
        return _analisar_imagem(alvo)
    if ext in _EXT_VIDEO:
        return _analisar_video(alvo)

    return {
        "tipo": f"arquivo genérico ({ext or 'sem extensão'})",
        "tamanho": _tamanho_legivel(os.path.getsize(alvo)),
        "indicios_tecnologia": [],
        "detalhes": {},
        "limitacoes": [f"Extensão '{ext}' não tem um analisador específico -- só reportei o tamanho."],
    }


def formatar_relatorio(alvo: str, resultado: dict) -> str:
    linhas = [f'Investigação de "{alvo}" -- tipo: {resultado["tipo"]}']
    if resultado.get("tamanho"):
        linhas.append(f"Tamanho: {resultado['tamanho']}")
    for chave, valor in resultado.get("detalhes", {}).items():
        linhas.append(f"{chave}: {valor}")
    if resultado.get("indicios_tecnologia"):
        linhas.append("Indícios de tecnologia:")
        linhas.extend(f"- {i}" for i in resultado["indicios_tecnologia"])
    if resultado.get("limitacoes"):
        linhas.append("Limitações desta análise:")
        linhas.extend(f"- {lim}" for lim in resultado["limitacoes"])
    return "\n".join(linhas)
