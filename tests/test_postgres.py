"""Integração com PostgreSQL real, em banco temporário exclusivo para cada teste."""
import os
import uuid
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from psycopg import sql
from starlette.testclient import TestClient

from app.banco import conectar, conectar_leitura
from scripts.migrar_sqlite import migrar


@pytest.fixture
def pg_url():
    base = os.environ.get("TEST_DATABASE_URL")
    if not base:
        pytest.skip("TEST_DATABASE_URL não configurada")
    nome = "teste_atribuicao_" + uuid.uuid4().hex
    partes = urlsplit(base)
    url = urlunsplit((partes.scheme, partes.netloc, "/" + nome, partes.query, partes.fragment))
    with psycopg.connect(base, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nome)))
    try:
        yield url
    finally:
        with psycopg.connect(base, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(nome)))


def test_migracao_preserva_dados_sequencias_e_recusa_destino_ocupado(pg_url, tmp_path):
    origem = tmp_path / "origem.db"
    con = conectar(origem)
    with con:
        con.execute("INSERT INTO eventos (id, anon_id, tipo, canal, momento) VALUES (42, 'aparelho', 'visita', 'E-mail', ?)",
                    ("2026-10-01T00:00:00+00:00",))
        con.execute("INSERT INTO consentimentos (anon_id, versao, aceito, juncao, momento) VALUES ('aparelho', 'v2', 1, 1, ?)",
                    ("2026-10-01T00:00:00+00:00",))
    con.close()
    assert migrar(origem, pg_url)["eventos"] == 1
    destino = conectar(pg_url, criar=False)
    assert destino.execute("SELECT id, canal FROM eventos").fetchone()["canal"] == "E-mail"
    with destino:
        destino.execute("INSERT INTO eventos (anon_id, tipo, momento) VALUES (?, 'visita', ?)",
                        ("outro", "2026-10-02T00:00:00+00:00"))
    assert destino.execute("SELECT MAX(id) FROM eventos").fetchone()[0] == 43
    destino.close()
    with pytest.raises(ValueError, match="Destino não está vazio"):
        migrar(origem, pg_url)
    assert conectar(origem).execute("SELECT COUNT(*) FROM eventos").fetchone()[0] == 1


def test_api_postgres_e_ga4_somente_leitura(pg_url, monkeypatch):
    from app import main
    from scripts.importar_ga4 import gravar

    monkeypatch.setattr(main, "CAMINHO_BANCO", pg_url)
    monkeypatch.setattr(main, "CAMINHO_GA4", pg_url)
    monkeypatch.setattr(main, "REPLICAS", 2)
    main._cache_painel.clear()
    evento = ("ga4-id", None, "visita", "E-mail", None, None, None, None, "computador", 0, "2020-12-01T00:00:00+00:00")
    gravar(pg_url, [evento], [])
    invalido = ("ga4-id", None, "tipo-invalido", "E-mail", None, None, None, None, "computador", 0,
                "2020-12-01T00:00:00+00:00")
    with pytest.raises(psycopg.errors.CheckViolation):
        gravar(pg_url, [invalido], [])
    con_ga4 = conectar_leitura(pg_url)
    assert con_ga4.execute("SELECT COUNT(*) FROM eventos").fetchone()[0] == 1
    con_ga4.close()
    with TestClient(main.app) as cliente:
        assert cliente.post("/api/consentimento", json={"anon_id": "aparelho-1", "aceito": True, "versao": "v2"}).status_code == 200
        dados = {"anon_id": "aparelho-1", "id_evento": "visita-123", "tipo": "visita"}
        assert cliente.post("/api/evento", json=dados).status_code == 200
        assert cliente.post("/api/evento", json=dados).status_code == 200
        assert cliente.get("/api/painel", headers={"authorization": "Bearer " + main.exigir_admin.__globals__["_TOKEN"]}).status_code == 200
    con = conectar(pg_url, criar=False)
    assert con.execute("SELECT COUNT(*) FROM eventos").fetchone()[0] == 1
    con.close()
    ga4 = conectar_leitura(pg_url)
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        ga4.execute("DELETE FROM eventos")
    ga4.close()
