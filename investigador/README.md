# investigador/ — Investigador Universal

Módulo novo (não altera nada do que já existia): dado um arquivo (EXE,
DLL, APK, PDF, imagem, vídeo) ou uma URL, tenta identificar
tecnologias/arquitetura/bibliotecas usadas e sinaliza pontos de
atenção, por heurística de assinatura.

## Análise estática e passiva, por design

- **Arquivos locais**: só LÊ bytes/metadados -- **nunca executa** o
  arquivo analisado. Rodar um `.exe`/`.apk` desconhecido "pra ver o que
  faz" seria de fato perigoso, e não é isso que este módulo faz.
- **Sites**: um único request HTTP de leitura (cabeçalhos + HTML da
  página pedida) -- **nunca varredura ativa** (sem fuzzing de
  parâmetro, sem tentar SQLi/XSS, sem varrer portas). Varredura ativa
  contra um site que não é seu, sem autorização, é pentest de verdade
  e está fora do escopo deste módulo por design.

## Limitação honesta

Isso é reconhecimento por assinatura/heurística (extensão, magic
bytes, strings legíveis, imports de DLL, estrutura de zip/APK,
cabeçalhos HTTP) — **não é engenharia reversa de verdade** (sem
desmontagem/decompilação) e **não é um scanner de vulnerabilidades
real** (sem consulta a base de CVE, sem fuzzing, sem exploração). Serve
pra um retrato rápido de "o que é isso e com o que foi feito", não um
laudo de segurança completo — todo resultado relatado inclui os
"indícios" encontrados e as limitações da análise, nunca uma alegação
de certeza absoluta.

## O que cada tipo de arquivo reporta

| Tipo | O que é lido | Precisa de |
|---|---|---|
| `.exe`/`.dll` | Strings legíveis (busca por marcador de tecnologia: PyInstaller, .NET, Electron, Qt, Unity...); arquitetura + DLLs importadas | `pefile` (opcional) pra arquitetura/DLLs -- funciona sem, só com strings |
| `.apk` | Estrutura do zip: Flutter/React Native/Cordova por arquivo característico, arquiteturas nativas presentes, se está assinado | nenhuma (usa `zipfile` da stdlib) |
| `.pdf` | Metadados (producer/creator/páginas), presença de JavaScript/anexo/ação automática | `pypdf` (opcional) pros metadados -- detecção de JS/anexo funciona sem |
| Imagem | Formato, resolução, EXIF (câmera, software, **alerta se tiver GPS**) | `Pillow` (opcional, já usado por `visao/`) |
| Vídeo | Codec, resolução, duração | binário `ffprobe` (parte do ffmpeg) no PATH |
| Site (URL) | Cabeçalhos (Server, X-Powered-By), fingerprint de framework/CMS no HTML (WordPress, Shopify, Next.js, Laravel...), ausência de cabeçalhos de segurança comuns | nenhuma (usa `urllib` da stdlib) |

Sem nenhuma dependência opcional instalada, ainda funciona com o nível
básico (extensão, tamanho, estrutura de zip, strings, cabeçalhos HTTP)
-- as libs só destravam detalhes mais profundos.

## Comandos

```
investiga o arquivo C:\caminho\app.exe
analisa esse apk: C:\caminho\app.apk
descubra tudo sobre https://exemplo.com
```

## Uso programático

```python
import investigador

resultado = investigador.analisar(r"C:\caminho\app.exe")
# {"tipo": "executável (PE)", "tamanho": "12.3MB",
#  "indicios_tecnologia": [...], "detalhes": {...}, "limitacoes": [...]}

print(investigador.formatar_relatorio(r"C:\caminho\app.exe", resultado))
```

## Instalação

```bash
pip install -r requirements-investigador.txt
```
