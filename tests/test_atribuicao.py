from datetime import datetime, timedelta

import pytest

from app.atribuicao import Jornada, atribuir, comparar, efeitos_remocao

T0 = datetime(2026, 10, 1, 12, 0)


def jornada(*canais, converteu=True, valor=100.0, dias_entre=1.0):
    toques = [(c, T0 + timedelta(days=i * dias_entre)) for i, c in enumerate(canais)]
    return Jornada(toques, converteu, valor if converteu else 0.0, toques[-1][1] if converteu else None)


J = jornada("Busca paga", "E-mail", "Social orgânico", "Direto")


def test_primeiro_toque():
    assert atribuir([J], "primeiro_toque").conversoes == {
        "Busca paga": 1.0, "E-mail": 0.0, "Social orgânico": 0.0, "Direto": 0.0,
    }


def test_ultimo_toque_pula_direto():
    r = atribuir([J], "ultimo_toque").conversoes
    assert r["Social orgânico"] == 1.0 and r["Direto"] == 0.0


def test_ultimo_toque_jornada_so_direto():
    assert atribuir([jornada("Direto", "Direto")], "ultimo_toque").conversoes["Direto"] == 1.0


def test_linear():
    assert all(v == pytest.approx(0.25) for v in atribuir([J], "linear").conversoes.values())


def test_posicao():
    r = atribuir([J], "posicao").conversoes
    assert r["Busca paga"] == pytest.approx(0.4)
    assert r["Direto"] == pytest.approx(0.4)
    assert r["E-mail"] == pytest.approx(0.1)
    assert atribuir([jornada("A", "B")], "posicao").conversoes == {"A": 0.5, "B": 0.5}


def test_decaimento_meia_vida():
    # Toque 7 dias antes da conversão vale metade do toque no dia da conversão.
    r = atribuir([jornada("Antigo", "Recente", dias_entre=7)], "decaimento_temporal").conversoes
    assert r["Antigo"] / r["Recente"] == pytest.approx(0.5)


def test_receita_acompanha_peso():
    r = atribuir([jornada("A", "B", valor=300)], "linear")
    assert r.receita == {"A": 150.0, "B": 150.0}


def test_todo_modelo_distribui_exatamente_as_conversoes():
    jornadas = [J, jornada("E-mail"), jornada("Busca paga", "Direto"), jornada("Display", converteu=False)]
    for modelo, r in comparar(jornadas).items():
        assert sum(r.conversoes.values()) == pytest.approx(3), modelo
        assert sum(r.receita.values()) == pytest.approx(300), modelo


def test_markov_canal_sem_saida_nao_recebe_credito():
    # Display só aparece em jornadas que não convertem.
    jornadas = [jornada("Busca paga")] * 5 + [jornada("Display", converteu=False)] * 5
    efeitos = efeitos_remocao(jornadas)
    assert efeitos["Display"] == pytest.approx(0)
    assert efeitos["Busca paga"] == pytest.approx(1)


def test_markov_canal_indispensavel():
    # Toda conversão passa por E-mail: removê-lo zera a conversão.
    jornadas = [jornada("Social orgânico", "E-mail"), jornada("Busca paga", "E-mail")]
    assert efeitos_remocao(jornadas)["E-mail"] == pytest.approx(1)


def test_markov_primeira_ordem_nao_lembra_a_origem():
    """Limitação conhecida, registrada como teste.

    A→C converte, B→C não converte. Intuitivamente A merece mais que B. Mas na
    cadeia de primeira ordem, o estado C não sabe de onde a pessoa veio: de C
    converte-se com 50% venha de A ou de B, e os dois recebem o mesmo crédito.
    Corrigir exige cadeia de ordem maior (estado = par de canais) ou valores
    de Shapley.
    """
    jornadas = [jornada("A", "C"), jornada("B", "C", converteu=False)]
    efeitos = efeitos_remocao(jornadas)
    assert efeitos["A"] == pytest.approx(efeitos["B"])


def test_jornadas_vazias():
    assert atribuir([], "markov").conversoes == {}
    assert atribuir([], "linear").conversoes == {}
