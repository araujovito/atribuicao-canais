import os

os.environ["ATRIBUICAO_BANCO"] = ":memory:"
os.environ["ATRIBUICAO_CHAVE_HMAC"] = "chave-de-teste"

import pytest
from fastapi.testclient import TestClient

from app import main

CELULAR = {"user-agent": "Mozilla/5.0 (Linux; Android 14) Mobile"}
PC = {"user-agent": "Mozilla/5.0 (X11; Linux x86_64)"}


@pytest.fixture
def cliente():
    for tabela in ("eventos", "vinculos", "consentimentos"):
        main.con.execute(f"DELETE FROM {tabela}")
    return TestClient(main.app)


def aceitar(cliente, anon):
    cliente.post("/api/consentimento", json={"anon_id": anon, "aceito": True, "versao": "v1"})


def test_sem_consentimento_nao_grava(cliente):
    r = cliente.post("/api/evento", json={"anon_id": "aparelho-1", "tipo": "visita"})
    assert r.status_code == 403
    assert main.con.execute("SELECT COUNT(*) FROM eventos").fetchone()[0] == 0


def test_consentimento_revogado_vale(cliente):
    aceitar(cliente, "aparelho-1")
    cliente.post("/api/consentimento", json={"anon_id": "aparelho-1", "aceito": False, "versao": "v1"})
    assert cliente.post("/api/evento", json={"anon_id": "aparelho-1", "tipo": "visita"}).status_code == 403


def test_minimizacao(cliente):
    aceitar(cliente, "aparelho-1")
    cliente.post("/api/evento", headers=CELULAR, json={
        "anon_id": "aparelho-1", "tipo": "conversao", "valor": 50,
        "referrer": "https://busca.exemplo/?q=meu+cpf+123", "email": "ana@exemplo.com",
    })
    linha = dict(main.con.execute("SELECT * FROM eventos").fetchone())
    assert linha["referrer_host"] == "busca.exemplo"
    assert linha["aparelho"] == "celular"
    assert "ana@exemplo.com" not in str(linha)


def test_jornada_celular_para_computador(cliente):
    # Ana clica no anúncio pelo celular...
    aceitar(cliente, "celular-ana")
    r = cliente.post("/api/evento", headers=CELULAR, json={
        "anon_id": "celular-ana", "tipo": "visita", "utm_source": "google", "utm_medium": "cpc",
    })
    assert r.json()["canal"] == "Busca paga"
    cliente.post("/api/identificar", json={"anon_id": "celular-ana", "email": "ana@exemplo.com"})
    # ...e compra dias depois no computador, digitando o endereço.
    aceitar(cliente, "computador-ana")
    cliente.post("/api/evento", headers=PC, json={"anon_id": "computador-ana", "tipo": "visita"})
    cliente.post("/api/evento", headers=PC, json={
        "anon_id": "computador-ana", "tipo": "conversao", "valor": 200, "email": "Ana@Exemplo.com",
    })

    p = cliente.get("/api/painel").json()
    assert p["resumo"]["conversoes_entre_aparelhos"] == 1
    assert p["modelos"]["ultimo_toque"]["receita"] == {"Busca paga": 200.0, "Direto": 0.0}
    # Sem a junção, o anúncio some e a venda fica com Direto.
    assert p["sem_juncao"]["ultimo_toque"]["receita"] == {"Direto": 200.0}


def test_exclusao_pela_api(cliente):
    aceitar(cliente, "celular-ana")
    cliente.post("/api/evento", json={"anon_id": "celular-ana", "tipo": "visita", "email": "ana@exemplo.com"})
    r = cliente.request("DELETE", "/api/titular", json={"email": "ana@exemplo.com"})
    assert r.json()["apagados"]["eventos_identificados"] == 1
    assert main.con.execute("SELECT COUNT(*) FROM eventos").fetchone()[0] == 0
