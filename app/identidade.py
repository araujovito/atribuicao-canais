"""Junção de identidade entre aparelhos (celular + computador = mesma pessoa).

Só existe uma fonte confiável para isso sem dados de terceiros: a própria
pessoa se identificar (login, cadastro, formulário). Cada aparelho tem um
identificador anônimo (`anon_id`, gerado no navegador depois do
consentimento); quando a pessoa se identifica, o aparelho ganha um vínculo
com o identificador pseudonimizado dela (`pessoa_id`, um HMAC do e-mail —
ver app/privacidade.py).

Regra de resolução, por evento:
1. Evento que já veio com `pessoa_id` pertence a essa pessoa.
2. Evento anônimo de um aparelho vinculado a exatamente UMA pessoa pertence
   a ela — inclusive os eventos de ANTES do login. É isso que liga o clique
   no anúncio pelo celular à compra no computador.
3. Aparelho vinculado a DUAS ou mais pessoas (notebook da família, computador
   de lan house) fica ambíguo: os eventos anônimos dele continuam anônimos.

Por que não um union-find simples ligando tudo que se toca: no computador
compartilhado, ele funde duas pessoas diferentes numa só, e a jornada de uma
passa a dar crédito pelas compras da outra. Errar para "não juntei" custa
um toque perdido; errar para "juntei errado" corrompe as duas jornadas.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable


def mapa_aparelhos(vinculos: Iterable[tuple[str, str]]) -> dict[str, set[str]]:
    """anon_id -> conjunto de pessoa_id que já se identificaram nele."""
    mapa: dict[str, set[str]] = defaultdict(set)
    for anon_id, pessoa_id in vinculos:
        mapa[anon_id].add(pessoa_id)
    return dict(mapa)


def resolver(anon_id: str, pessoa_id: str | None, mapa: dict[str, set[str]]) -> str:
    """Identificador canônico de um evento: 'p:<pessoa>' ou 'a:<aparelho>'.

    O prefixo impede que um anon_id e um pessoa_id iguais por acaso colidam.
    """
    if pessoa_id:
        return f"p:{pessoa_id}"
    pessoas = mapa.get(anon_id, set())
    if len(pessoas) == 1:
        return f"p:{next(iter(pessoas))}"
    return f"a:{anon_id}"


def aparelhos_ambiguos(mapa: dict[str, set[str]]) -> set[str]:
    return {anon for anon, pessoas in mapa.items() if len(pessoas) > 1}
