"""Funil por canal de entrada: visita → login → carrinho → compra.

Para cada pessoa (com aparelhos juntados), o canal de entrada é o do
primeiro toque com canal. Conta-se quem chegou a cada etapa.

Funil aberto, não sequencial: cada etapa conta quem a alcançou, mesmo
pulando a anterior. Na loja, login é opcional — quem compra sem entrar
sumiria de um funil sequencial e a taxa de compra sairia menor do que é.
A consequência é que login pode ficar abaixo de carrinho, e isso é
informação (quantos compram sem se identificar), não erro.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict

from app import tempo
from app.identidade import mapa_aparelhos, resolver

ETAPAS = ("visita", "login", "carrinho", "compra")


def funil(con: sqlite3.Connection) -> dict:
    mapa = mapa_aparelhos(con.execute("SELECT anon_id, pessoa_id FROM vinculos"))
    entrada: dict[str, tuple] = {}  # pessoa -> (momento, canal) do primeiro toque
    alcancou: dict[str, set[str]] = defaultdict(set)

    for ev in con.execute("SELECT anon_id, pessoa_id, tipo, canal, momento FROM eventos"):
        dono = resolver(ev["anon_id"], ev["pessoa_id"], mapa)
        if ev["tipo"] == "visita":
            alcancou[dono].add("visita")
            if ev["canal"]:
                t = tempo.ler(ev["momento"])
                if dono not in entrada or t < entrada[dono][0]:
                    entrada[dono] = (t, ev["canal"])
        else:
            alcancou[dono].add("compra")
    for et in con.execute("SELECT anon_id, etapa FROM etapas"):
        alcancou[resolver(et["anon_id"], None, mapa)].add(et["etapa"])

    por_canal: dict[str, dict[str, int]] = defaultdict(lambda: dict.fromkeys(ETAPAS, 0))
    total = dict.fromkeys(ETAPAS, 0)
    for dono, etapas in alcancou.items():
        if dono not in entrada:
            continue  # sem nenhuma visita com origem: não há canal para atribuir
        canal = entrada[dono][1]
        for e in etapas:
            por_canal[canal][e] += 1
            total[e] += 1
    return {"etapas": list(ETAPAS), "total": total, "por_canal": dict(por_canal)}
