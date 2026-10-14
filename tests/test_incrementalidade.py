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
    # (1,96 + 0,84) × erro-padrão
    erro = (0.3 * 0.7 / 400 + 0.2 * 0.8 / 400) ** 0.5
    assert r["efeito_minimo_detectavel"] == pytest.approx(2.8016 * erro, rel=1e-3)


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
