"""Modelos de atribuição: quanto crédito cada canal recebe por uma conversão.

Cinco modelos de regra (os mesmos que GA4, RD Station e afins mostram) e um
modelo baseado em dados (cadeia de Markov com efeito de remoção).

Entrada comum: uma lista de `Jornada` — a sequência de toques de UMA pessoa
(já com aparelhos juntados, ver app/identidade.py) até converter ou até a
janela acabar sem conversão.

Decisões:
- Último toque ignora Direto quando há outro canal na jornada. É a convenção
  do GA4 ("último clique não direto"): quem digita o endereço já conhecia a
  marca por algum canal, e dar a venda para Direto esconde esse canal. Os
  outros modelos de regra contam Direto como qualquer canal — a comparação no
  painel mostra a diferença.
- Decaimento temporal com meia-vida de 7 dias, o padrão do Google Ads.
  Parâmetro, não constante: dá para testar outras meias-vidas.
- Posição: 40% primeiro, 40% último, 20% dividido no meio. Com dois toques,
  50/50; com um, 100%.
- Markov usa TODAS as jornadas, inclusive as que não converteram — é delas
  que sai a informação de que um canal leva a lugar nenhum. Os modelos de
  regra só olham jornadas que converteram.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

DIRETO = "Direto"
INICIO, CONVERSAO, NULO = "(início)", "(conversão)", "(nulo)"


@dataclass
class Jornada:
    toques: list[tuple[str, datetime]]  # (canal, momento), em ordem cronológica
    converteu: bool = False
    valor: float = 0.0
    momento_conversao: datetime | None = None
    pessoa: str = field(default="")
    aparelhos: frozenset[str] = frozenset()  # anon_ids envolvidos; >1 = jornada entre aparelhos

    @property
    def canais(self) -> list[str]:
        return [canal for canal, _ in self.toques]


# --- modelos de regra: cada um devolve o peso de cada toque (soma 1) --------


def _primeiro(j: Jornada) -> list[float]:
    return [1.0] + [0.0] * (len(j.toques) - 1)


def _ultimo_nao_direto(j: Jornada) -> list[float]:
    pesos = [0.0] * len(j.toques)
    for i in range(len(j.toques) - 1, -1, -1):
        if j.toques[i][0] != DIRETO:
            pesos[i] = 1.0
            return pesos
    pesos[-1] = 1.0  # jornada só de Direto: aí o crédito é dele mesmo
    return pesos


def _linear(j: Jornada) -> list[float]:
    n = len(j.toques)
    return [1.0 / n] * n


def _decaimento(j: Jornada, meia_vida_dias: float = 7.0) -> list[float]:
    fim = j.momento_conversao or j.toques[-1][1]
    brutos = [0.5 ** (max((fim - t).total_seconds(), 0) / 86400 / meia_vida_dias) for _, t in j.toques]
    total = sum(brutos)
    return [b / total for b in brutos]


def _posicao(j: Jornada) -> list[float]:
    n = len(j.toques)
    if n == 1:
        return [1.0]
    if n == 2:
        return [0.5, 0.5]
    meio = 0.2 / (n - 2)
    return [0.4] + [meio] * (n - 2) + [0.4]


MODELOS_REGRA = {
    "primeiro_toque": _primeiro,
    "ultimo_toque": _ultimo_nao_direto,
    "linear": _linear,
    "decaimento_temporal": _decaimento,
    "posicao": _posicao,
}

NOMES = {
    "primeiro_toque": "Primeiro toque",
    "ultimo_toque": "Último toque (não direto)",
    "linear": "Linear",
    "decaimento_temporal": "Decaimento temporal (meia-vida 7 dias)",
    "posicao": "Posição (40/20/40)",
    "markov": "Markov 1ª ordem (efeito de remoção)",
    "markov2": "Markov 2ª ordem (lembra o canal anterior)",
}


@dataclass
class Resultado:
    conversoes: dict[str, float]  # canal -> conversões atribuídas (fracionárias)
    receita: dict[str, float]  # canal -> receita atribuída


def atribuir_regra(jornadas: list[Jornada], modelo: str) -> Resultado:
    regra = MODELOS_REGRA[modelo]
    conv: dict[str, float] = defaultdict(float)
    rec: dict[str, float] = defaultdict(float)
    for j in jornadas:
        if not j.converteu or not j.toques:
            continue
        for (canal, _), peso in zip(j.toques, regra(j)):
            conv[canal] += peso
            rec[canal] += peso * j.valor
    return Resultado(dict(conv), dict(rec))


# --- Markov -----------------------------------------------------------------
#
# Estado = os últimos `ordem` canais. Na 1ª ordem, o estado é só o canal atual
# e a cadeia não sabe de onde a pessoa veio (limitação escrita em teste). Na
# 2ª ordem, o estado é o par (anterior, atual): "C vindo de A" e "C vindo de B"
# viram estados diferentes, com probabilidades de conversão próprias.
#
# O preço é dado: com 9 canais são até 9 estados na 1ª ordem e até 90 na 2ª,
# e cada transição é estimada com menos jornadas. Por isso as duas ficam no
# painel, lado a lado, e a margem de erro (bootstrap) mostra a diferença.

Estado = tuple[str, ...]


def _estados_do_caminho(canais: list[str], ordem: int) -> list[Estado]:
    caminho = [INICIO, *canais]
    return [tuple(caminho[max(0, i - ordem + 1): i + 1]) for i in range(len(caminho))]


def _transicoes(jornadas: list[Jornada], ordem: int = 1) -> dict[Estado, dict]:
    contagem: dict[Estado, dict] = defaultdict(lambda: defaultdict(int))
    for j in jornadas:
        if not j.toques:
            continue
        estados = _estados_do_caminho(j.canais, ordem)
        for de, para in zip(estados, estados[1:]):
            contagem[de][para] += 1
        contagem[estados[-1]][CONVERSAO if j.converteu else NULO] += 1
    return {
        de: {para: n / sum(destinos.values()) for para, n in destinos.items()}
        for de, destinos in contagem.items()
    }


def _prob_conversao(trans: dict[Estado, dict], removido: str | None = None) -> float:
    """Probabilidade de sair de (início) e chegar em (conversão).

    p(s) = soma_t T(s,t) p(t), com p(conversão)=1 e p(nulo)=0. Remover um
    canal = todo estado que o contém vira (nulo).

    Resolvido por Gauss-Seidel, não por eliminação de Gauss: a matriz é
    esparsa (cada estado leva a poucos outros), e com os ~90 estados da 2ª
    ordem a eliminação em Python puro custaria segundos por chamada — e o
    bootstrap chama centenas de vezes. Converge porque toda jornada termina
    em conversão ou nulo (cadeia absorvente).
    """
    vivos = [e for e in trans if removido not in e]
    p = dict.fromkeys(vivos, 0.0)
    for _ in range(10_000):
        delta = 0.0
        for e in vivos:
            novo = 0.0
            for t, pr in trans[e].items():
                if t == CONVERSAO:
                    novo += pr
                elif t != NULO and t in p:
                    novo += pr * p[t]
            delta = max(delta, abs(novo - p[e]))
            p[e] = novo
        if delta < 1e-12:
            break
    return p.get((INICIO,), 0.0)


def efeitos_remocao(jornadas: list[Jornada], ordem: int = 1) -> dict[str, float]:
    """Queda relativa na probabilidade de conversão ao remover cada canal."""
    trans = _transicoes(jornadas, ordem)
    if (INICIO,) not in trans:
        return {}
    base = _prob_conversao(trans)
    if base == 0:
        return {}
    canais = {c for j in jornadas for c in j.canais}
    return {c: (base - _prob_conversao(trans, removido=c)) / base for c in sorted(canais)}


def atribuir_markov(jornadas: list[Jornada], ordem: int = 1) -> Resultado:
    """Divide conversões e receita totais na proporção do efeito de remoção.

    A receita usa a mesma proporção das conversões: a cadeia modela SE a
    pessoa converte, não QUANTO gasta.
    """
    efeitos = efeitos_remocao(jornadas, ordem)
    soma = sum(efeitos.values())
    total_conv = sum(1 for j in jornadas if j.converteu and j.toques)
    total_rec = sum(j.valor for j in jornadas if j.converteu and j.toques)
    if not soma:
        return Resultado({}, {})
    return Resultado(
        {c: total_conv * e / soma for c, e in efeitos.items()},
        {c: total_rec * e / soma for c, e in efeitos.items()},
    )


def atribuir(jornadas: list[Jornada], modelo: str) -> Resultado:
    if modelo == "markov":
        return atribuir_markov(jornadas, ordem=1)
    if modelo == "markov2":
        return atribuir_markov(jornadas, ordem=2)
    return atribuir_regra(jornadas, modelo)


def comparar(jornadas: list[Jornada]) -> dict[str, Resultado]:
    return {m: atribuir(jornadas, m) for m in NOMES}
