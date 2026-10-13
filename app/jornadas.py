"""Monta jornadas (sequência de toques até a conversão) a partir dos eventos.

Regras:
- Um toque é uma visita com canal (o rastreador só manda a visita de entrada
  de cada sessão; navegação interna nem sai do navegador).
- Cada conversão fecha uma jornada com os toques dentro da janela de
  retroatividade (30 dias por padrão, o mesmo do GA4 para conversões que não
  são de aquisição). Toques fora da janela não recebem crédito.
- Conversão sem nenhum toque na janela vira uma jornada de um toque Direto,
  como no GA4: alguém chegou sem origem rastreável.
- Toques depois da última conversão formam uma jornada que não converteu —
  é a matéria-prima do Markov para saber quais canais não levam a nada.

`juntar=False` agrupa por aparelho em vez de pessoa. Serve para mostrar no
painel o que a atribuição diria sem a junção entre aparelhos.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.atribuicao import DIRETO, Jornada
from app.identidade import aparelhos_ambiguos, mapa_aparelhos, resolver

JANELA_DIAS = 30


@dataclass
class Montagem:
    jornadas: list[Jornada]
    pessoas_identificadas: int
    aparelhos: int
    aparelhos_ambiguos: int
    conversoes_entre_aparelhos: int


def montar(con: sqlite3.Connection, janela_dias: int = JANELA_DIAS, juntar: bool = True) -> Montagem:
    mapa = mapa_aparelhos(con.execute("SELECT anon_id, pessoa_id FROM vinculos"))
    if not juntar:
        mapa = {}

    grupos: dict[str, list[sqlite3.Row]] = defaultdict(list)
    linhas = con.execute(
        "SELECT anon_id, pessoa_id, tipo, canal, valor, momento FROM eventos ORDER BY momento, id"
    )
    for ev in linhas:
        dono = resolver(ev["anon_id"], ev["pessoa_id"] if juntar else None, mapa)
        grupos[dono].append(ev)

    janela = timedelta(days=janela_dias)
    jornadas: list[Jornada] = []
    for dono, eventos in grupos.items():
        pendentes: list[tuple[str, datetime, str]] = []
        for ev in eventos:
            t = datetime.fromisoformat(ev["momento"])
            if ev["tipo"] == "visita":
                if ev["canal"]:
                    pendentes.append((ev["canal"], t, ev["anon_id"]))
                continue
            na_janela = [p for p in pendentes if t - p[1] <= janela]
            if not na_janela:
                na_janela = [(DIRETO, t, ev["anon_id"])]
            jornadas.append(Jornada(
                toques=[(c, m) for c, m, _ in na_janela],
                converteu=True,
                valor=ev["valor"] or 0.0,
                momento_conversao=t,
                pessoa=dono,
                aparelhos=frozenset({a for _, _, a in na_janela} | {ev["anon_id"]}),
            ))
            pendentes = []
        if pendentes:
            jornadas.append(Jornada(
                toques=[(c, m) for c, m, _ in pendentes],
                pessoa=dono,
                aparelhos=frozenset(a for _, _, a in pendentes),
            ))

    n_aparelhos = con.execute("SELECT COUNT(DISTINCT anon_id) FROM eventos").fetchone()[0]
    n_pessoas = con.execute("SELECT COUNT(DISTINCT pessoa_id) FROM vinculos").fetchone()[0]
    return Montagem(
        jornadas=jornadas,
        pessoas_identificadas=n_pessoas,
        aparelhos=n_aparelhos,
        aparelhos_ambiguos=len(aparelhos_ambiguos(mapa)),
        conversoes_entre_aparelhos=sum(1 for j in jornadas if j.converteu and len(j.aparelhos) > 1),
    )
