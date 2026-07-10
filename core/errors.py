"""Erros de domínio apresentados de forma segura na interface."""


class ClipForgeError(RuntimeError):
    """Erro esperado do aplicativo, adequado para exibição ao usuário."""


class DependencyUnavailableError(ClipForgeError):
    """Uma dependência local opcional ou executável não está disponível."""


class InvalidMediaError(ClipForgeError):
    """A mídia recebida não pode ser usada pelo pipeline solicitado."""


class JobCancelledError(ClipForgeError):
    """O usuário cancelou o trabalho em andamento."""
