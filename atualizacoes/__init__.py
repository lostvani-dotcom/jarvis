from atualizacoes.updater import aplicar_atualizacao, check_for_updates, iniciar, is_git_repo
from atualizacoes.version import VERSION

__all__ = ["VERSION", "check_for_updates", "aplicar_atualizacao", "iniciar", "is_git_repo", "status"]


def status() -> dict:
    report = check_for_updates()
    return {
        "disponivel": True,
        "motivo": f"v{VERSION} -- {report['motivo']}",
        "detalhes": report,
    }
