from app.banco import conectar
from app.funis import funil


def inserir(con, anon, tipo, canal=None, pessoa=None, momento="2026-10-01T10:00:00+00:00"):
    con.execute("INSERT INTO eventos (anon_id, pessoa_id, tipo, canal, momento) VALUES (?, ?, ?, ?, ?)",
                (anon, pessoa, tipo, canal, momento))


def etapa(con, anon, nome):
    con.execute("INSERT INTO etapas (anon_id, etapa, momento) VALUES (?, ?, '2026-10-01T10:05:00+00:00')", (anon, nome))


def test_funil_aberto_por_canal_de_entrada():
    con = conectar(":memory:")
    # Ana: entra por Busca paga, faz login, monta carrinho e compra.
    inserir(con, "cel-ana", "visita", "Busca paga")
    etapa(con, "cel-ana", "login"); etapa(con, "cel-ana", "carrinho")
    inserir(con, "cel-ana", "conversao", momento="2026-10-01T11:00:00+00:00")
    # Bruno: entra por Display, monta carrinho e compra SEM login.
    inserir(con, "pc-bruno", "visita", "Display")
    etapa(con, "pc-bruno", "carrinho")
    inserir(con, "pc-bruno", "conversao", momento="2026-10-01T11:00:00+00:00")
    # Caio: só visita.
    inserir(con, "cel-caio", "visita", "Display")
    f = funil(con)
    assert f["por_canal"]["Busca paga"] == {"visita": 1, "login": 1, "carrinho": 1, "compra": 1}
    assert f["por_canal"]["Display"] == {"visita": 2, "login": 0, "carrinho": 1, "compra": 1}
    assert f["total"] == {"visita": 3, "login": 1, "carrinho": 2, "compra": 2}


def test_canal_de_entrada_e_o_primeiro_toque_da_pessoa_juntada():
    con = conectar(":memory:")
    con.execute("INSERT INTO vinculos VALUES ('celular', 'ana', 'x'), ('computador', 'ana', 'x')")
    inserir(con, "computador", "visita", "Direto", momento="2026-10-05T10:00:00+00:00")
    inserir(con, "celular", "visita", "Social pago", momento="2026-10-01T10:00:00+00:00")
    inserir(con, "computador", "conversao", pessoa="ana", momento="2026-10-05T10:10:00+00:00")
    f = funil(con)
    assert list(f["por_canal"]) == ["Social pago"]
    assert f["por_canal"]["Social pago"]["compra"] == 1
