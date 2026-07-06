# server/ — Servidor HTTP local (app do celular)

Servidor HTTP 100% biblioteca padrão (`http.server`) -- **zero
dependência nova**. Deixa o app companion do celular
([`app_android/`](../app_android/)) conversar com a MESMA instância de
Jarvis que já está rodando na GUI ou no terminal: memória e histórico
são compartilhados, não é uma sessão separada.

Sobe automaticamente junto com o Jarvis (`core/jarvis.py`, gated por
`modulos.servidor` em `config.json`, ligado por padrão) -- não precisa
rodar nada à parte.

## Rede local (LAN) só

Escuta em todas as interfaces (`0.0.0.0`) pra o celular alcançar o IP
do PC na mesma Wi-Fi -- igual ao ADB sem fio
([`dispositivos/`](../dispositivos/README.md)), isso **nunca** mexe em
configuração de roteador/port-forwarding, então o servidor continua
fora do alcance da internet a menos que você mesmo exponha isso
manualmente (não recomendado).

## Autenticação

Todo endpoint (exceto `/`, `/status`, `/app.apk`, `/qr.png` e
`/app/version` -- página de instalação e metadados públicos) exige o
header `Authorization: Bearer <token>`. O token é gerado uma vez e
persistido em `config.json` -> `servidor.token`. O app do celular
recebe esse token automaticamente ao descobrir o Jarvis na rede (ver
"Descoberta automática" abaixo) -- não precisa mais copiar/digitar.

## Endpoints

| Método | Rota | Auth | Corpo | Resposta |
|---|---|---|---|---|
| GET | `/` | não | -- | página HTML de instalação (QR code + botão "Baixar APK") -- abra `http://<ip-do-pc>:8765/` no navegador |
| GET | `/status` | não | -- | `{"ok": true, "nome": "Jarvis"}` -- só pra o app confirmar que achou o servidor certo |
| GET | `/app.apk` | não | -- | baixa o APK do app companion ([`app_android/`](../app_android/README.md)) |
| GET | `/qr.png` | não | -- | QR code (PNG) apontando pra `/app.apk` -- requer `qrcode` instalado (`pip install qrcode`); sem isso, `/` cai pro link direto |
| GET | `/app/version` | não | -- | `{"versionCode": int, "versionName": str}` -- lido de `app_android/app/build.gradle.kts`; o app compara com a própria versão e se autoatualiza se tiver uma mais nova |
| POST | `/chat` | sim | `{"text": str}` | `{"resposta": str}` -- roda `jarvis.process(text)` de verdade |
| POST | `/notify` | sim | `{"pacote", "titulo", "texto"}` | `{"ok": true}` -- o app manda notificações capturadas nativamente (ver `automacao/notification_inbox.py`) |
| GET | `/poll` | sim | -- | `{"mensagens": [...]}` -- long-poll simples: lembretes/comentários que o Jarvis quis avisar por conta própria |
| GET | `/device/commands` | sim | -- | `{"comando": {...} \| null}` -- o app pergunta, em polling curto em segundo plano, se o Jarvis pediu algo (bateria, abrir app, volume, lanterna, achar o celular, armazenamento, app em primeiro plano -- ver `automacao/phone_commands.py`) |
| POST | `/device/result` | sim | `{"id", "resultado"}` | `{"ok": bool}` -- o app devolve o resultado do comando que executou |

## Descoberta automática (`discovery.py`)

O app do celular acha o IP do PC e conecta sozinho, sem digitar nada:
manda um broadcast UDP `JARVIS_DISCOVER` na porta **8766**, e
`start_discovery()` (subido junto com o servidor HTTP) responde
`{"nome": "Jarvis", "porta_http": <porta>, "token": <token>}`.

**Decisão consciente de segurança**: a resposta inclui o token, de
propósito -- eliminar a fricção de copiar um token de 32 caracteres
manualmente. O efeito colateral: qualquer aparelho capaz de mandar
esse broadcast na mesma rede Wi-Fi consegue descobrir e usar o
Jarvis, não só o celular do dono. O perímetro de confiança passa a
ser "estar na Wi-Fi de casa", não mais "conhecer o token". Aceitável
pra uso doméstico pessoal; se a rede for compartilhada com gente não
confiável, desligue `modulos.servidor` ou edite `discovery.py` pra
tirar o token da resposta.

Melhor-esforço: se a porta UDP não puder ser aberta, só loga um
aviso -- o app continua funcionando com IP/porta/token digitados
manualmente.

## Configuração (`config.json` -> `servidor`)

| Chave | Efeito |
|---|---|
| `porta` | porta TCP do servidor HTTP (padrão `8765`) |
| `token` | gerado automaticamente no primeiro início; pode ser sobrescrito manualmente |

## Uso programático

```python
from core.jarvis import Jarvis
from server import start_server

jarvis = Jarvis(user_id="voce")
httpd, token = start_server(jarvis)
print("Token:", token)
```
