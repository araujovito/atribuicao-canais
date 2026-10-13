import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Arquivo, não :memory: — cada requisição abre a própria conexão, e cada
# conexão a ":memory:" seria um banco vazio diferente.
os.environ["ATRIBUICAO_BANCO"] = str(Path(tempfile.mkdtemp()) / "teste.db")
os.environ["ATRIBUICAO_CHAVE_HMAC"] = "chave-de-teste"
os.environ["ATRIBUICAO_TOKEN_ADMIN"] = "token-de-teste"

import pytest
from fastapi.testclient import TestClient

from app import limite, main
from app.banco import conectar


def consultar(sql):
    con = conectar(main.CAMINHO_BANCO)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()

CELULAR = {"user-agent": "Mozilla/5.0 (Linux; Android 14) Mobile"}
PC = {"user-agent": "Mozilla/5.0 (X11; Linux x86_64)"}
ADMIN = {"authorization": "Bearer token-de-teste"}


@pytest.fixture
def cliente():
    con = conectar(main.CAMINHO_BANCO)
    with con:
        for tabela in ("eventos", "vinculos", "consentimentos"):
            con.execute(f"DELETE FROM {tabela}")
    con.close()
    limite.zerar()
    with TestClient(main.app) as c:
        yield c


def aceitar(cliente, anon):
    cliente.post("/api/consentimento", json={"anon_id": anon, "aceito": True, "versao": "v1"})


def test_sem_consentimento_nao_grava(cliente):
    r = cliente.post("/api/evento", json={"anon_id": "aparelho-1", "tipo": "visita"})
    assert r.status_code == 403
    assert consultar("SELECT COUNT(*) FROM eventos")[0][0] == 0


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
    linha = dict(consultar("SELECT * FROM eventos")[0])
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

    p = cliente.get("/api/painel", headers=ADMIN).json()
    assert p["resumo"]["conversoes_entre_aparelhos"] == 1
    assert p["modelos"]["ultimo_toque"]["receita"] == {"Busca paga": 200.0, "Direto": 0.0}
    # Sem a junção, o anúncio some e a venda fica com Direto.
    assert p["sem_juncao"]["ultimo_toque"]["receita"] == {"Direto": 200.0}


def test_exclusao_exige_codigo_do_email(cliente, monkeypatch):
    enviados = []
    monkeypatch.setattr(main.correio, "enviar", lambda para, assunto, corpo: enviados.append((para, corpo)))
    aceitar(cliente, "celular-ana")
    cliente.post("/api/evento", json={"anon_id": "celular-ana", "tipo": "visita", "email": "ana@exemplo.com"})

    # Sem código, ou com código inventado, nada é apagado.
    assert cliente.request("DELETE", "/api/titular", json={"email": "ana@exemplo.com"}).status_code == 422
    r = cliente.request("DELETE", "/api/titular", json={"email": "ana@exemplo.com", "codigo": "123456"})
    assert r.status_code == 403

    cliente.post("/api/titular/pedido", json={"email": "ana@exemplo.com"})
    para, corpo = enviados[-1]
    codigo = next(p for p in corpo.split() if p.isdigit() and len(p) == 6)
    assert para == "ana@exemplo.com"
    r = cliente.request("DELETE", "/api/titular", json={"email": "ana@exemplo.com", "codigo": codigo})
    assert r.json()["apagados"]["eventos_identificados"] == 1
    assert consultar("SELECT COUNT(*) FROM eventos")[0][0] == 0
    # Código é de uso único.
    assert cliente.request("DELETE", "/api/titular", json={"email": "ana@exemplo.com", "codigo": codigo}).status_code == 403


def test_pedido_nao_revela_se_email_existe(cliente, monkeypatch):
    monkeypatch.setattr(main.correio, "enviar", lambda *a: None)
    aceitar(cliente, "celular-ana")
    cliente.post("/api/evento", json={"anon_id": "celular-ana", "tipo": "visita", "email": "ana@exemplo.com"})
    com = cliente.post("/api/titular/pedido", json={"email": "ana@exemplo.com"}).json()
    sem = cliente.post("/api/titular/pedido", json={"email": "ninguem@exemplo.com"}).json()
    assert com == sem


def test_exclusao_pelo_atendimento_exige_token(cliente):
    aceitar(cliente, "celular-ana")
    cliente.post("/api/evento", json={"anon_id": "celular-ana", "tipo": "visita", "email": "ana@exemplo.com"})
    assert cliente.request("DELETE", "/api/admin/titular", json={"email": "ana@exemplo.com"}).status_code == 401
    r = cliente.request("DELETE", "/api/admin/titular", headers=ADMIN, json={"email": "ana@exemplo.com"})
    assert r.json()["apagados"]["eventos_identificados"] == 1


def test_requisicoes_simultaneas(cliente):
    # Antes, uma conexão única era compartilhada entre as threads do servidor.
    aceitar(cliente, "aparelho-concorrente")

    def enviar(_):
        return cliente.post("/api/evento", json={"anon_id": "aparelho-concorrente", "tipo": "visita"}).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        codigos = list(pool.map(enviar, range(40)))
    assert codigos == [200] * 40
    assert consultar("SELECT COUNT(*) FROM eventos")[0][0] == 40


def test_painel_exige_token(cliente):
    assert cliente.get("/api/painel").status_code == 401
    assert cliente.get("/api/painel", headers={"authorization": "Bearer errado"}).status_code == 401
    assert cliente.get("/api/painel", headers=ADMIN).status_code == 200


def test_retencao_exige_token_e_nao_esvazia_o_banco(cliente):
    aceitar(cliente, "aparelho-1")
    cliente.post("/api/evento", json={"anon_id": "aparelho-1", "tipo": "visita"})
    assert cliente.post("/api/retencao?dias=0").status_code == 401
    assert cliente.post("/api/retencao?dias=0", headers=ADMIN).status_code == 422
    assert cliente.post("/api/retencao?dias=30", headers=ADMIN).json()["eventos_apagados"] == 0
    assert consultar("SELECT COUNT(*) FROM eventos")[0][0] == 1


def test_limite_de_eventos_por_ip(cliente):
    aceitar(cliente, "aparelho-1")
    codigos = [cliente.post("/api/evento", json={"anon_id": "aparelho-1", "tipo": "visita"}).status_code
               for _ in range(61)]
    assert codigos[:60] == [200] * 60
    assert codigos[60] == 429
    assert consultar("SELECT COUNT(*) FROM eventos")[0][0] == 60


def test_limite_de_pedidos_de_exclusao(cliente, monkeypatch):
    monkeypatch.setattr(main.correio, "enviar", lambda *a: None)
    codigos = [cliente.post("/api/titular/pedido", json={"email": f"x{i}@exemplo.com"}).status_code for i in range(6)]
    assert codigos == [200] * 5 + [429]


def test_anon_id_com_caracteres_estranhos(cliente):
    r = cliente.post("/api/consentimento", json={"anon_id": "<script>alert(1)</script>", "aceito": True, "versao": "v1"})
    assert r.status_code == 422


def test_atras_de_proxy_vale_o_ip_que_o_proxy_acrescentou(cliente, monkeypatch):
    monkeypatch.setattr(limite, "ATRAS_DE_PROXY", True)
    aceitar(cliente, "aparelho-1")
    # O cliente forja o primeiro endereço a cada requisição; o último é do proxy.
    codigos = [
        cliente.post("/api/evento", headers={"x-forwarded-for": f"10.0.0.{i}, 200.1.1.1"},
                     json={"anon_id": "aparelho-1", "tipo": "visita"}).status_code
        for i in range(61)
    ]
    assert codigos[60] == 429
