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

O intervalo de 95% usa a aproximação normal da diferença de proporções.
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


def analisar(con: sqlite3.Connection, agora: datetime | None = None, janela_dias: int = JANELA_DIAS) -> dict[str, dict]:
    mapa = mapa_aparelhos(con.execute("SELECT anon_id, pessoa_id FROM vinculos"))
    compraram = {
        resolver(r["anon_id"], r["pessoa_id"], mapa)
        for r in con.execute("SELECT anon_id, pessoa_id FROM eventos WHERE tipo = 'conversao'")
    }
    grupos: dict[str, dict[str, set[str]]] = defaultdict(lambda: {"tratamento": set(), "controle": set()})
    limite = tempo.texto((agora or tempo.agora()) - timedelta(days=janela_dias))
    tratados_total: dict[str, set[str]] = defaultdict(set)
    for r in con.execute("SELECT anon_id, canal, grupo, momento FROM experimentos"):
        unidade = resolver(r["anon_id"], None, mapa)
        if r["grupo"] == "tratamento":
            tratados_total[r["canal"]].add(unidade)
        if r["momento"] <= limite:
            grupos[r["canal"]][r["grupo"]].add(unidade)

    resultado = {}
    for canal, g in grupos.items():
        n_t, n_c = len(g["tratamento"]), len(g["controle"])
        if not n_t or not n_c:
            continue
        p_t = len(g["tratamento"] & compraram) / n_t
        p_c = len(g["controle"] & compraram) / n_c
        efeito = p_t - p_c
        erro = math.sqrt(p_t * (1 - p_t) / n_t + p_c * (1 - p_c) / n_c)
        lo, hi = efeito - Z95 * erro, efeito + Z95 * erro
        resultado[canal] = {
            "pessoas_tratamento": n_t,
            "pessoas_controle": n_c,
            # Tratados sem o filtro da janela: é a população sobre a qual os
            # modelos de atribuição distribuem crédito, para comparar por pessoa.
            "pessoas_tratamento_total": len(tratados_total[canal]),
            "taxa_tratamento": p_t,
            "taxa_controle": p_c,
            "efeito": efeito,
            "efeito_ic": [lo, hi],
            "compras_incrementais": efeito * n_t,
            "compras_incrementais_ic": [lo * n_t, hi * n_t],
            "significativo": lo > 0 or hi < 0,
            # Menor efeito que este tamanho de amostra detectaria 80% das vezes.
            "efeito_minimo_detectavel": (Z95 + Z80) * erro,
        }
    return resultado
