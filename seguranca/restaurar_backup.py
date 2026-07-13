"""
seguranca/restaurar_backup.py
================================
Restaura um backup COMPLETO (ver seguranca/backup.py:criar_pacote_completo)
-- só roda localmente, na linha de comando, de propósito: restaurar
sobrescreve o banco de dados, a config e a chave de criptografia
atuais, uma operação destrutiva demais pra expor como endpoint remoto
(alguém com o token da rede local, ou um bug no app, poderia disparar
isso sem querer -- diferente do backup em si, que só LÊ dados).

Uso:
    python -m seguranca.restaurar_backup caminho/para/ultron_completo_XXXXXXXX.zip

Pede confirmação explícita (digitar "restaurar") antes de sobrescrever
qualquer coisa, e sempre guarda uma cópia do estado ATUAL antes de
restaurar (em data/backups/antes_restaurar_*), pra dar pra desfazer se
o backup escolhido for o errado.
"""

import os
import shutil
import sys
import zipfile
from datetime import datetime


def restaurar(caminho_zip: str):
    if not os.path.isfile(caminho_zip):
        print(f"Arquivo não encontrado: {caminho_zip}")
        return

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    destinos = {
        "jarvis.db": os.path.join(base_dir, "data", "jarvis.db"),
        "config.json": os.path.join(base_dir, "config", "config.json"),
        ".jarvis.key": os.path.join(base_dir, "data", ".jarvis.key"),
    }

    with zipfile.ZipFile(caminho_zip, "r") as z:
        nomes_no_zip = set(z.namelist())

    presentes = nomes_no_zip & set(destinos.keys())
    if not presentes:
        print("Esse .zip não contém nenhum dos arquivos esperados (jarvis.db, config.json, .jarvis.key).")
        return

    print(f"O backup '{os.path.basename(caminho_zip)}' contém: {', '.join(sorted(presentes))}")
    print(
        "\nRESTAURAR vai SOBRESCREVER o banco de dados, config e/ou chave de criptografia "
        "atuais deste Ultron. Uma cópia do estado atual é feita antes, em data/backups/, "
        "mas confirme mesmo assim."
    )
    resposta = input("Digite 'restaurar' pra confirmar: ").strip().lower()
    if resposta != "restaurar":
        print("Cancelado.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backups_dir = os.path.join(base_dir, "data", "backups")
    os.makedirs(backups_dir, exist_ok=True)
    for nome in presentes:
        caminho_atual = destinos[nome]
        if os.path.isfile(caminho_atual):
            copia = os.path.join(backups_dir, f"antes_restaurar_{timestamp}_{nome}")
            shutil.copy2(caminho_atual, copia)
            print(f"Estado atual de {nome} salvo em {copia}")

    with zipfile.ZipFile(caminho_zip, "r") as z:
        for nome in presentes:
            caminho_atual = destinos[nome]
            os.makedirs(os.path.dirname(caminho_atual), exist_ok=True)
            with z.open(nome) as origem, open(caminho_atual, "wb") as dest:
                shutil.copyfileobj(origem, dest)
            print(f"Restaurado: {nome}")

    print("\nRestauração concluída. Reinicie o Ultron pra usar o estado restaurado.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python -m seguranca.restaurar_backup caminho/para/backup.zip")
        sys.exit(1)
    restaurar(sys.argv[1])
