"""Margem de erro dos créditos por bootstrap.

Cada percentual do painel é uma estimativa: com outras pessoas no mesmo
período, sairia outro número. O bootstrap mede quanto ele balançaria:
sorteia, com reposição, o mesmo número de PESSOAS da amostra (não de
jornadas — as jornadas de uma pessoa não são independentes entre si),
recalcula todos os modelos e guarda a participação de cada canal. O
intervalo de 95% vai do percentil 2,5 ao 97,5 dessas réplicas.

Leitura: dois canais cujos intervalos se sobrepõem não estão separados
pelos dados; a diferença entre eles pode ser sorteio.
"""

from __future__ import annotations

import random
from collections import defaultdict

from app.atribuicao import NOMES, Jornada, atribuir

REPLICAS = 100


def _participacao(valores: dict[str, float]) -> dict[str, float]:
    total = sum(valores.values())
    return {c: v / total for c, v in valores.items()} if total else {}


def _percentil(ordenados: list[float], q: float) -> float:
    if not ordenados:
        return 0.0
    pos = q * (len(ordenados) - 1)
    baixo = int(pos)
    alto = min(baixo + 1, len(ordenados) - 1)
    return ordenados[baixo] + (ordenados[alto] - ordenados[baixo]) * (pos - baixo)


def intervalos(jornadas: list[Jornada], replicas: int = REPLICAS, semente: int = 0) -> dict:
    """{modelo: {medida: {canal: [p2.5, p97.5]}}}, em participação (0 a 1)."""
    por_pessoa: dict[str, list[Jornada]] = defaultdict(list)
    for j in jornadas:
        por_pessoa[j.pessoa].append(j)
    pessoas = list(por_pessoa.values())
    if not pessoas:
        return {}
    rng = random.Random(semente)
    canais = {c for j in jornadas for c in j.canais}
    amostras = {m: {"conversoes": defaultdict(list), "receita": defaultdict(list)} for m in NOMES}
    for _ in range(replicas):
        sorteio = [j for grupo in rng.choices(pessoas, k=len(pessoas)) for j in grupo]
        for m in NOMES:
            r = atribuir(sorteio, m)
            for medida, valores in (("conversoes", r.conversoes), ("receita", r.receita)):
                part = _participacao(valores)
                for c in canais:
                    amostras[m][medida][c].append(part.get(c, 0.0))
    return {
        m: {
            medida: {c: [_percentil(sorted(v), 0.025), _percentil(sorted(v), 0.975)] for c, v in por_canal.items()}
            for medida, por_canal in medidas.items()
        }
        for m, medidas in amostras.items()
    }
