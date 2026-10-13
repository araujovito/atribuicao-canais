"""Envio de e-mail transacional (código de confirmação).

O protótipo não tem servidor de e-mail: a mensagem vai para o log do
servidor, que faz o papel da caixa de entrada. Em produção, esta função é o
único ponto a trocar (SMTP, Amazon SES, SendGrid); quem chama não muda.
"""

from __future__ import annotations

import logging

log = logging.getLogger("uvicorn.error")


def enviar(para: str, assunto: str, corpo: str) -> None:
    log.warning("[e-mail simulado] para=%s assunto=%r: %s", para, assunto, corpo)
