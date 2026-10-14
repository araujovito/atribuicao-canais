"""Qual modelo chega mais perto da verdade — só possível em dado fictício.

Com dado real ninguém sabe quantas compras cada canal causou. O gerador sabe,
porque escreveu a regra de compra, e grava na tabela `verdade` a soma das
contribuições de cada canal (valor de Shapley sobre a chance de compra de
cada pessoa; ver scripts/gerar_dados.py).

Comparação por participação, não por número absoluto: os modelos dividem
TODAS as compras entre os canais, inclusive as que aconteceriam sem canal
nenhum (a chance-base do gerador), enquanto a verdade só conta o que os
canais causaram. A medida é a distância de variação total: metade da soma
das diferenças de participação, lida como "fração do crédito que está no
canal errado". 0% = igual à verdade.
"""

from __future__ import annotations

import sqlite3

from app.atribuicao import Resultado


def participacao(valores: dict[str, float]) -> dict[str, float]:
    total = sum(valores.values())
    return {c: v / total for c, v in valores.items()} if total else {}


def comparar_com_verdade(con: sqlite3.Connection, resultados: dict[str, Resultado]) -> dict | None:
    verdade = {r["canal"]: r["compras"] for r in con.execute("SELECT canal, compras FROM verdade")}
    if not verdade:
        return None
    alvo = participacao(verdade)
    erros = {}
    for modelo, r in resultados.items():
        part = participacao(r.conversoes)
        canais = set(alvo) | set(part)
        erros[modelo] = sum(abs(part.get(c, 0) - alvo.get(c, 0)) for c in canais) / 2
    return {"participacao": alvo, "credito_no_canal_errado": erros}
