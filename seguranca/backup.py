"""
seguranca/backup.py
======================
Backup automático de `data/jarvis.db` (cópia com timestamp), com
limpeza dos backups mais antigos além do limite configurado.
"""

import glob
import os
import shutil
from datetime import datetime

from config.settings import get_settings
from core.database import DB_PATH

BACKUP_DIR = os.path.join(os.path.dirname(DB_PATH), "backups")


def create_backup() -> str:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    if not os.path.isfile(DB_PATH):
        raise FileNotFoundError(f"Banco de dados não encontrado em {DB_PATH}")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(BACKUP_DIR, f"jarvis_{timestamp}.db")
    shutil.copy2(DB_PATH, dest)
    _cleanup_old_backups()
    return dest


def list_backups() -> list:
    if not os.path.isdir(BACKUP_DIR):
        return []
    return sorted(glob.glob(os.path.join(BACKUP_DIR, "jarvis_*.db")), reverse=True)


def _cleanup_old_backups():
    max_files = int(get_settings().get("seguranca.backup_max_arquivos", 10))
    for old_file in list_backups()[max_files:]:
        try:
            os.remove(old_file)
        except OSError:
            pass


def maybe_auto_backup():
    """Chamado no startup do Ultron (core/jarvis.py). Só cria backup se
    `seguranca.backup_automatico=true` E já se passou
    `seguranca.backup_intervalo_horas` desde o último backup. Retorna o
    caminho do novo backup, ou None se nenhum foi necessário."""
    settings = get_settings()
    if not settings.get("seguranca.backup_automatico", True):
        return None

    interval_hours = float(settings.get("seguranca.backup_intervalo_horas", 24))
    backups = list_backups()
    if backups:
        last_mtime = datetime.fromtimestamp(os.path.getmtime(backups[0]))
        elapsed_hours = (datetime.now() - last_mtime).total_seconds() / 3600
        if elapsed_hours < interval_hours:
            return None

    return create_backup()
