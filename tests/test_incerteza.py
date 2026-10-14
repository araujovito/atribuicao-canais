from datetime import datetime, timedelta, timezone

from app.atribuicao import Jornada
from app.incerteza import intervalos

T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)


def j(pessoa, *canais, converteu=True):
    toques = [(c, T0 + timedelta(days=i)) for i, c in enumerate(canais)]
    return Jornada(toques, converteu, 100.0 if converteu else 0.0, toques[-1][1], pessoa=pessoa)


def test_intervalo_contem_a_estimativa_e_encolhe_com_mais_dados():
    base = [j("a", "Busca paga"), j("b", "E-mail"), j("c", "Busca paga", "E-mail"), j("d", "Display", converteu=False)]
    pequeno = intervalos(base, replicas=200, semente=1)["linear"]["conversoes"]["Busca paga"]
    grande_dados = [Jornada(x.toques, x.converteu, x.valor, x.momento_conversao, pessoa=f"{x.pessoa}{k}")
                    for k in range(50) for x in base]
    grande = intervalos(grande_dados, replicas=200, semente=1)["linear"]["conversoes"]["Busca paga"]
    estimativa = 1.5 / 3  # Busca paga: 1 + 0,5 de 3 conversões
    assert pequeno[0] <= estimativa <= pequeno[1]
    assert grande[0] <= estimativa <= grande[1]
    assert (grande[1] - grande[0]) < (pequeno[1] - pequeno[0])


def test_reamostra_pessoas_e_nao_jornadas():
    # Duas jornadas da mesma pessoa saem juntas em toda réplica: se a pessoa
    # "x" entra, entram as duas. Com 1 pessoa só, não há variação nenhuma.
    so_uma = [j("x", "Busca paga"), j("x", "E-mail")]
    iv = intervalos(so_uma, replicas=50)["linear"]["conversoes"]
    assert iv["Busca paga"] == [0.5, 0.5]


def test_reproduzivel():
    base = [j("a", "Busca paga"), j("b", "E-mail"), j("c", "Display", converteu=False)]
    assert intervalos(base, 30, semente=3) == intervalos(base, 30, semente=3)
