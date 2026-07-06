"""
server/
=======
Servidor HTTP local do Ultron, pra um app no celular (ou qualquer
cliente HTTP na mesma rede) conversar com o Ultron remotamente -- ver
server/http_server.py e app_android/.
"""

from server.discovery import start_discovery
from server.http_server import start_server, get_or_create_token

__all__ = ["start_server", "get_or_create_token", "start_discovery"]
