"""Teste de incrementalidade: quanto um canal CAUSA de compras.

Os modelos de atribuição dividem as compras entre os canais que aparecem no
caminho; nenhum deles sabe o que teria acontecido sem o canal. O teste
responde isso com um grupo de controle sorteado:

- quem seria exposto ao anúncio é sorteado para tratamento (vê) ou controle
  (não vê). No método "ghost ads", a plataforma registra quem teria visto,
  então os dois grupos são comparáveis e só diferem no anúncio;
- efeito por pessoa = taxa de compra do tratamento − taxa do controle;
- compras incrementais = efeito × pessoas no tratamento: as compras que não
  teriam acontecido sem o anúncio.

O intervalo de 95% usa a combinação dos intervalos de Wilson (Newcombe).
Intervalo que cruza o zero = o teste não distingue o efeito de nenhum
efeito, com esse tamanho de amostra.

Dois vieses, os dois puxando o efeito para zero (achados ao comparar a
medida com o efeito verdadeiro do gerador, em 10 sementes):

1. Janela aberta. Quem foi sorteado há poucos dias ainda não teve tempo de
   comprar, e o tratamento — com mais toques, jornadas mais longas — perde
   mais compras por isso. Corrigido: só entra quem foi sorteado há mais que
   a janela de conversão (30 dias), a regra de "ler o teste depois que a
   janela fecha".
2. Diluição. A unidade é a pessoa com aparelhos juntados (app/identidade.py);
   quem não fez login vira uma unidade por aparelho, e o celular de quem
   comprou no computador conta como "não comprou", nos dois grupos. O efeito
   medido fica ~25% menor que o real. Não tem correção aqui: exigiria o
   identificador da plataforma de anúncios, que não é compartilhado.

Contaminação: num computador compartilhado, uma pessoa do controle e outra
exposta usam o mesmo aparelho, e o controle "vê" o anúncio. Também puxa o
efeito para zero; é pequena porque poucos aparelhos são compartilhados.

Poder: com centenas de pessoas por grupo, o teste só enxerga efeitos de
vários pontos percentuais. O efeito mínimo detectável (80% de poder, 5% de
significância) vai junto do resultado, para "não significativo" não ser
lido como "sem efeito".
"""

from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta

from app import tempo
from app.identidade import mapa_aparelhos, resolver

Z95 = 1.959964
Z80 = 0.841621  # poder de 80%
JANELA_DIAS = 30


def _wilson(k: int, n: int) -> tuple[float, float]:
    p = k / n
    z2 = Z95 * Z95
    centro = (p + z2 / (2 * n)) / (1 + z2 / n)
    margem = Z95 * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    return max(0.0, centro - margem), min(1.0, centro + margem)


def analisar(con: sqlite3.Connection, agora: datetime | None = None, janela_dias: int = JANELA_DIAS) -> dict[str, dict]:
    mapa = mapa_aparelhos(con.execute("SELECT anon_id, pessoa_id FROM vinculos"))
    compras: dict[str, list[datetime]] = defaultdict(list)
    for r in con.execute("SELECT anon_id, pessoa_id, momento FROM eventos WHERE tipo = 'conversao'"):
        compras[resolver(r["anon_id"], r["pessoa_id"], mapa)].append(tempo.ler(r["momento"]))
    grupos = defaultdict(lambda: {"tratamento": {}, "controle": {}})
    instante = agora or tempo.agora()
    limite = instante - timedelta(days=janela_dias)
    for r in con.execute("SELECT anon_id, canal, grupo, momento FROM experimentos"):
        unidade = resolver(r["anon_id"], None, mapa)
        inicio = tempo.ler(r["momento"])
        grupo = grupos[r["canal"]][r["grupo"]]
        grupo[unidade] = min(grupo.get(unidade, inicio), inicio)

    resultado = {}
    for canal, g in grupos.items():
        # A unidade experimental precisa pertencer a um único grupo. Bases
        # externas podem sortear dois aparelhos antes de eles serem ligados à
        # mesma pessoa; nesse caso, excluímos a unidade contaminada dos dois
        # braços e mostramos quantas foram afetadas.
        contaminadas = g["tratamento"].keys() & g["controle"].keys()
        tratados_total = len(g["tratamento"].keys() - contaminadas)
        elegiveis = {grupo: {u: t for u, t in unidades.items() if u not in contaminadas and t <= limite}
                     for grupo, unidades in g.items()}
        n_t, n_c = len(elegiveis["tratamento"]), len(elegiveis["controle"])
        if not n_t or not n_c:
            resultado[canal] = {"pessoas_tratamento": n_t, "pessoas_controle": n_c,
                                "pessoas_contaminadas": len(contaminadas), "disponivel": False}
            continue
        def contar(unidades: dict[str, datetime]) -> int:
            return sum(any(inicio <= t <= inicio + timedelta(days=janela_dias) for t in compras[u])
                       for u, inicio in unidades.items())

        k_t, k_c = contar(elegiveis["tratamento"]), contar(elegiveis["controle"])
        p_t, p_c = k_t / n_t, k_c / n_c
        efeito = p_t - p_c
        lt, ht = _wilson(k_t, n_t)
        lc, hc = _wilson(k_c, n_c)
        lo = efeito - math.hypot(p_t - lt, hc - p_c)
        hi = efeito + math.hypot(ht - p_t, p_c - lc)
        # Estimativa aproximada sob a hipótese nula, com suavização para
        # não afirmar poder infinito quando não há eventos observados.
        base = (k_t + k_c + 1) / (n_t + n_c + 2)
        mde = min(1.0, (Z95 + Z80) * math.sqrt(base * (1 - base) * (1 / n_t + 1 / n_c)))
        resultado[canal] = {
            "disponivel": True,
            "pessoas_tratamento": n_t,
            "pessoas_controle": n_c,
            "pessoas_contaminadas": len(contaminadas),
            # Tratados sem o filtro da janela: é a população sobre a qual os
            # modelos de atribuição distribuem crédito, para comparar por pessoa.
            "pessoas_tratamento_total": tratados_total,
            "taxa_tratamento": p_t,
            "taxa_controle": p_c,
            "efeito": efeito,
            "efeito_ic": [lo, hi],
            "compras_incrementais": efeito * n_t,
            "compras_incrementais_ic": [lo * n_t, hi * n_t],
            "significativo": lo > 0 or hi < 0,
            # Menor efeito que este tamanho de amostra detectaria 80% das vezes.
            "efeito_minimo_detectavel": mde,
        }
    return resultado
