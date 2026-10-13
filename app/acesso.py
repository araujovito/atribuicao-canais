"""Acesso de administrador às rotas de análise e manutenção.

Coleta (consentimento, evento, identificação) é pública por natureza: o
navegador de qualquer visitante chama essas rotas. Já o painel mostra o
comportamento de todos os visitantes, e a retenção apaga dados — essas exigem
o token de administrador no cabeçalho `Authorization: Bearer <token>`.

O token vem de ATRIBUICAO_TOKEN_ADMIN. Sem a variável, o servidor sorteia um
token novo a cada subida e o escreve no log, para o painel funcionar em
desenvolvimento sem deixar uma senha fixa conhecida no código.

Um token fixo, e não login com usuário e senha: o protótipo tem um único
perfil (quem analisa). Com vários perfis, o caminho seria OAuth/OIDC na frente
do serviço, não uma tabela de senhas feita à mão.
"""

from __future__ import annotations

import hmac
import logging
import os
import secrets

from fastapi import Header, HTTPException

log = logging.getLogger("uvicorn.error")

_TOKEN = os.environ.get("ATRIBUICAO_TOKEN_ADMIN") or ""
if not _TOKEN:
    _TOKEN = secrets.token_urlsafe(24)
    log.warning("ATRIBUICAO_TOKEN_ADMIN ausente; token de administrador desta execução: %s", _TOKEN)


def token_admin() -> str:
    return _TOKEN


def exigir_admin(authorization: str | None = Header(default=None)) -> None:
    esquema, _, valor = (authorization or "").partition(" ")
    # compare_digest: o tempo da comparação não revela quantos caracteres acertaram.
    if esquema.lower() != "bearer" or not hmac.compare_digest(valor.encode(), _TOKEN.encode()):
        raise HTTPException(401, "token de administrador ausente ou inválido",
                            headers={"WWW-Authenticate": "Bearer"})
