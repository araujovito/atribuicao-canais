"""Limite de requisições por IP, em memória.

Sem limite, qualquer um inventa anon_ids e enche o banco de eventos falsos,
ou tenta códigos de exclusão sem parar. Cada rota pública tem a própria
cota (janela deslizante): uma pessoa real navegando nunca chega perto.

O IP só existe aqui, em memória, pelo tempo da janela; não é gravado no
banco (minimização, ver app/banco.py).

Atrás de proxy (Render, Railway), o IP de quem conecta é o do proxy. Com
ATRIBUICAO_ATRAS_DE_PROXY=1, vale o ÚLTIMO endereço do X-Forwarded-For —
o que o proxy acrescentou. O primeiro é o que o cliente diz ser, e o cliente
escreve o que quiser ali.

Limite: a memória é por processo. Com vários processos ou várias máquinas,
cada um conta sozinho; aí o contador vai para o Redis ou para o próprio
proxy. Para um processo único, como o protótipo roda, basta.
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

ATRAS_DE_PROXY = os.environ.get("ATRIBUICAO_ATRAS_DE_PROXY") == "1"

_janelas: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_trava = threading.Lock()
_ultima_faxina = 0.0


def ip_do_cliente(request: Request) -> str:
    if ATRAS_DE_PROXY:
        encaminhado = request.headers.get("x-forwarded-for", "")
        if encaminhado:
            return encaminhado.split(",")[-1].strip()
    return request.client.host if request.client else "desconhecido"


def _faxina(agora: float, maior_janela: float) -> None:
    global _ultima_faxina
    if agora - _ultima_faxina < 60:
        return
    _ultima_faxina = agora
    for chave in [k for k, fila in _janelas.items() if not fila or agora - fila[-1] > maior_janela]:
        del _janelas[chave]


def limitar(nome: str, maximo: int, janela_s: float):
    """Dependência FastAPI: no máximo `maximo` chamadas por IP a cada `janela_s` segundos."""

    def dependencia(request: Request) -> None:
        agora = time.monotonic()
        chave = (nome, ip_do_cliente(request))
        with _trava:
            fila = _janelas[chave]
            while fila and agora - fila[0] > janela_s:
                fila.popleft()
            if len(fila) >= maximo:
                espera = int(janela_s - (agora - fila[0])) + 1
                raise HTTPException(429, "muitas requisições; tente de novo mais tarde",
                                    headers={"Retry-After": str(espera)})
            fila.append(agora)
            _faxina(agora, 3600)

    return dependencia


def zerar() -> None:
    with _trava:
        _janelas.clear()
