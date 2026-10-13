"""Datas sempre em UTC, gravadas como texto ISO 8601 com o deslocamento.

O banco guarda `2026-10-13T15:00:00+00:00`, nunca a hora local sem fuso.
Sem isso, o mesmo código grava 12:00 no computador de casa e 15:00 num
servidor do Render (que roda em UTC), e a janela de 30 dias e o decaimento
temporal passam a medir horas erradas.

Como todo texto gravado tem o mesmo formato e o mesmo deslocamento, a ordem
alfabética é a ordem cronológica: as comparações de data no SQL
(`momento < ?`) continuam corretas.
"""

from __future__ import annotations

from datetime import datetime, timezone


def agora() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def texto(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValueError("data sem fuso: use app.tempo.agora() ou informe tzinfo")
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def ler(valor: str) -> datetime:
    dt = datetime.fromisoformat(valor)
    # Linhas gravadas antes desta regra não têm fuso; eram hora do servidor
    # local, e UTC é a leitura menos errada disponível.
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
