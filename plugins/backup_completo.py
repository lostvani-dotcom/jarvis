"""
plugins/backup_completo.py
=============================
Comando de chat pra gerar o backup COMPLETO baixável (banco de dados +
config + chave de criptografia, ver seguranca/backup.py). Diferente do
backup diário automático (só o .db) -- este é pensado pra restaurar o
Ultron inteiro numa máquina nova, ou depois de um desastre (ver
seguranca/restaurar_backup.py pra restaurar).

Comando:
    "faz um backup completo" -> gera o .zip e abre a pasta
"""

import os
import sys

from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin


class BackupCompletoPlugin(BasePlugin):
    name = "backup_completo"
    description = "Gera um backup completo (banco de dados + config + chave) pronto pra baixar/restaurar"
    triggers = ["backup completo"]

    def handle(self, text: str, context: dict):
        try:
            from seguranca.backup import criar_pacote_completo
            caminho = criar_pacote_completo()
        except Exception as e:
            return Answer(f"Não consegui gerar o backup completo: {e}", Confidence.GUESS)

        self._abrir_pasta(caminho)
        return Answer(
            f"Backup completo gerado em:\n{caminho}\n\n"
            "Contém o banco de dados, a configuração e a chave de criptografia -- guarde num "
            "lugar seguro (é a chave pra decifrar o histórico do RedCore). Pra restaurar numa "
            "máquina nova: `python -m seguranca.restaurar_backup <caminho do zip>`. Também dá "
            "pra baixar pelo celular em http://<ip-do-pc>:8765/backup/completo (exige o token).",
            Confidence.CONFIRMED,
        )

    def _abrir_pasta(self, caminho: str):
        try:
            pasta = os.path.dirname(caminho)
            if sys.platform == "win32":
                os.startfile(pasta)
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", pasta])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", pasta])
        except Exception:
            pass  # melhor-esforço -- o caminho já foi informado na resposta
