from datetime import datetime, timedelta, timezone

import pytest

from app.atribuicao import Resultado
from app.banco import conectar
from app.verdade import comparar_com_verdade
from scripts.gerar_dados import chance_de_compra, contribuicoes


def test_shapley_soma_o_efeito_total_da_jornada():
    for canais in (["Display", "Busca paga", "Busca paga"], ["E-mail", "Direto", "Social pago", "E-mail", "Busca orgânica", "Direto", "Afiliados"]):
        phi = contribuicoes(canais)
        assert sum(phi.values()) == pytest.approx(chance_de_compra(canais) - chance_de_compra([]))


def test_display_nao_causa_nada():
    assert contribuicoes(["Display", "E-mail"])["Display"] == pytest.approx(0)


def test_teto_de_toques_e_dividido_entre_canais():
    # 6 toques úteis, teto de 5: o sexto não soma nada sozinho, e o Shapley
    # reparte a perda entre os canais em vez de jogá-la em quem veio por último.
    phi = contribuicoes(["Direto"] * 3 + ["Afiliados"] * 3)
    assert phi["Direto"] == pytest.approx(phi["Afiliados"])


def test_credito_no_canal_errado():
    con = conectar(":memory:")
    assert comparar_com_verdade(con, {}) is None  # dado real: sem verdade
    con.executemany("INSERT INTO verdade VALUES (?, ?)", [("A", 30.0), ("B", 10.0)])
    resultados = {
        "igual": Resultado({"A": 3.0, "B": 1.0}, {}),
        "invertido": Resultado({"A": 1.0, "B": 3.0}, {}),
        "canal_novo": Resultado({"A": 3.0, "C": 1.0}, {}),
    }
    erros = comparar_com_verdade(con, resultados)["credito_no_canal_errado"]
    assert erros["igual"] == pytest.approx(0)
    assert erros["invertido"] == pytest.approx(0.5)
    assert erros["canal_novo"] == pytest.approx(0.25)
