from datetime import datetime, timedelta, timezone

import pytest

from app.banco import conectar
from app.incrementalidade import analisar
from app.tempo import texto

AGORA = datetime(2026, 10, 13, tzinfo=timezone.utc)
VELHO = texto(AGORA - timedelta(days=45))  # janela de conversão já fechou
RECENTE = texto(AGORA - timedelta(days=5))  # ainda aberta


def popular(con, canal, grupo, n, compram, momento=VELHO, prefixo=""):
    for i in range(n):
        anon = f"{prefixo}{grupo}{i}"
        con.execute("INSERT INTO experimentos VALUES (?, ?, ?, ?)", (anon, canal, grupo, momento))
        if i < compram:
            con.execute("INSERT INTO eventos (anon_id, tipo, valor, momento) VALUES (?, 'conversao', 10, ?)",
                        (anon, momento))


def test_efeito_e_intervalo():
    con = conectar(":memory:")
    popular(con, "Social pago", "tratamento", 400, 120)  # 30%
    popular(con, "Social pago", "controle", 400, 80)  # 20%
    r = analisar(con, agora=AGORA)["Social pago"]
    assert r["efeito"] == pytest.approx(0.10)
    assert r["compras_incrementais"] == pytest.approx(40)
    assert r["efeito_ic"][0] > 0 and r["significativo"]
    assert 0 < r["efeito_minimo_detectavel"] < 1


def test_sem_efeito_nao_e_significativo():
    con = conectar(":memory:")
    popular(con, "Display", "tratamento", 200, 40)
    popular(con, "Display", "controle", 200, 40)
    r = analisar(con, agora=AGORA)["Display"]
    assert r["efeito"] == pytest.approx(0) and not r["significativo"]
    assert r["efeito_ic"][0] < 0 < r["efeito_ic"][1]


def test_so_le_quem_ja_fechou_a_janela():
    con = conectar(":memory:")
    popular(con, "Display", "tratamento", 100, 10)
    popular(con, "Display", "controle", 100, 10)
    # Sorteados há 5 dias: ainda não deu tempo de comprar; não entram na leitura.
    popular(con, "Display", "tratamento", 100, 0, momento=RECENTE, prefixo="r")
    r = analisar(con, agora=AGORA)["Display"]
    assert r["pessoas_tratamento"] == 100
    assert r["pessoas_tratamento_total"] == 200  # para comparar com o crédito dos modelos


def test_unidade_em_dois_grupos_e_excluida_da_analise():
    con = conectar(":memory:")
    popular(con, "Display", "tratamento", 10, 2)
    popular(con, "Display", "controle", 10, 2)
    # Os dois aparelhos passam a resolver para a mesma pessoa, embora tenham
    # sido sorteados para braços diferentes antes da identificação.
    con.execute("INSERT INTO vinculos VALUES (?, ?, ?)", ("tratamento0", "pessoa-x", VELHO))
    con.execute("INSERT INTO vinculos VALUES (?, ?, ?)", ("controle0", "pessoa-x", VELHO))
    r = analisar(con, agora=AGORA)["Display"]
    assert r["pessoas_contaminadas"] == 1
    assert r["pessoas_tratamento"] == 9
    assert r["pessoas_controle"] == 9


def test_compra_fora_da_janela_nao_conta():
    con = conectar(":memory:")
    popular(con, "Display", "tratamento", 2, 0)
    popular(con, "Display", "controle", 2, 0)
    for anon, instante in [("tratamento0", AGORA - timedelta(days=46)),
                           ("tratamento1", AGORA - timedelta(days=14))]:
        con.execute("INSERT INTO eventos (anon_id, tipo, valor, momento) VALUES (?, 'conversao', 1, ?)",
                    (anon, texto(instante)))
    assert analisar(con, agora=AGORA)["Display"]["taxa_tratamento"] == 0


def test_amostra_extrema_nao_apresenta_certeza_falsa():
    con = conectar(":memory:")
    popular(con, "Display", "tratamento", 1, 1)
    popular(con, "Display", "controle", 1, 0)
    r = analisar(con, agora=AGORA)["Display"]
    assert r["efeito_ic"][0] < 0 < r["efeito_ic"][1]
    assert not r["significativo"] and r["efeito_minimo_detectavel"] > 0


def test_conflito_recente_remove_unidade_e_exibe_grupo_vazio():
    con = conectar(":memory:")
    popular(con, "Display", "tratamento", 1, 0, momento=RECENTE)
    popular(con, "Display", "controle", 1, 0)
    for anon in ("tratamento0", "controle0"):
        con.execute("INSERT INTO vinculos VALUES (?, ?, ?)", (anon, "mesma-pessoa", VELHO))
    r = analisar(con, agora=AGORA)["Display"]
    assert r["pessoas_contaminadas"] == 1
    assert not r["disponivel"] and r["pessoas_controle"] == 0
