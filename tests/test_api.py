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
        for tabela in ("eventos", "vinculos", "consentimentos", "etapas"):
            con.execute(f"DELETE FROM {tabela}")
    con.close()
    limite.zerar()
    main._cache_painel.clear()
    with TestClient(main.app) as c:
        yield c


def aceitar(cliente, anon, juncao=True):
    cliente.post("/api/consentimento", json={"anon_id": anon, "aceito": True, "juncao": juncao, "versao": "v2"})


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


def test_painel_usa_cache_ate_os_dados_mudarem(cliente, monkeypatch):
    chamadas = []
    original = main.calcular_painel
    monkeypatch.setattr(main, "calcular_painel", lambda con, j: chamadas.append(j) or original(con, j))
    aceitar(cliente, "aparelho-1")
    cliente.post("/api/evento", json={"anon_id": "aparelho-1", "tipo": "conversao", "valor": 10})
    cliente.get("/api/painel", headers=ADMIN)
    cliente.get("/api/painel", headers=ADMIN)
    assert len(chamadas) == 1
    cliente.post("/api/evento", json={"anon_id": "aparelho-1", "tipo": "conversao", "valor": 10})
    p = cliente.get("/api/painel", headers=ADMIN).json()
    assert len(chamadas) == 2 and p["resumo"]["conversoes"] == 2
    cliente.get("/api/painel?janela_dias=7", headers=ADMIN)
    assert len(chamadas) == 3


def test_cache_percebe_troca_da_ultima_linha(cliente):
    # Sem AUTOINCREMENT, o id apagado volta: contagem e ids não bastam.
    aceitar(cliente, "aparelho-1")
    cliente.post("/api/evento", json={"anon_id": "aparelho-1", "tipo": "conversao", "valor": 10})
    antes = cliente.get("/api/painel", headers=ADMIN).json()["resumo"]["receita"]
    con = conectar(main.CAMINHO_BANCO)
    with con:
        con.execute("DELETE FROM eventos WHERE id = (SELECT MAX(id) FROM eventos)")
    con.close()
    cliente.post("/api/evento", json={"anon_id": "aparelho-1", "tipo": "conversao", "valor": 99})
    assert (antes, cliente.get("/api/painel", headers=ADMIN).json()["resumo"]["receita"]) == (10, 99)


def test_so_medicao_nao_liga_email_ao_aparelho(cliente):
    aceitar(cliente, "aparelho-1", juncao=False)
    r = cliente.post("/api/evento", json={"anon_id": "aparelho-1", "tipo": "conversao", "valor": 10,
                                          "email": "ana@exemplo.com"})
    assert r.status_code == 200  # a compra é medida...
    assert consultar("SELECT pessoa_id FROM eventos")[0][0] is None  # ...mas sem pessoa
    assert consultar("SELECT COUNT(*) FROM vinculos")[0][0] == 0
    assert cliente.post("/api/identificar", json={"anon_id": "aparelho-1", "email": "ana@exemplo.com"}).status_code == 403


def test_juncao_sem_medicao_nao_vale(cliente):
    cliente.post("/api/consentimento", json={"anon_id": "aparelho-1", "aceito": False, "juncao": True, "versao": "v2"})
    assert cliente.post("/api/identificar", json={"anon_id": "aparelho-1", "email": "a@exemplo.com"}).status_code == 403


def test_retirar_juncao_desfaz_ligacoes_do_aparelho(cliente):
    aceitar(cliente, "aparelho-1")
    cliente.post("/api/evento", json={"anon_id": "aparelho-1", "tipo": "conversao", "valor": 10, "email": "ana@exemplo.com"})
    aceitar(cliente, "aparelho-1", juncao=False)
    assert consultar("SELECT COUNT(*) FROM vinculos")[0][0] == 0
    assert consultar("SELECT pessoa_id FROM eventos")[0][0] is None
    # A medição continua valendo.
    assert cliente.post("/api/evento", json={"anon_id": "aparelho-1", "tipo": "visita"}).status_code == 200


def test_migra_banco_da_primeira_versao(tmp_path):
    import sqlite3
    caminho = tmp_path / "v1.db"
    antigo = sqlite3.connect(caminho)
    antigo.execute("CREATE TABLE consentimentos (id INTEGER PRIMARY KEY, anon_id TEXT NOT NULL, versao TEXT NOT NULL,"
                   " aceito INTEGER NOT NULL, momento TEXT NOT NULL)")
    antigo.execute("INSERT INTO consentimentos (anon_id, versao, aceito, momento) VALUES ('a', 'v1', 1, 'x')")
    antigo.commit(); antigo.close()
    con = conectar(caminho)
    assert tuple(con.execute("SELECT aceito, juncao FROM consentimentos").fetchone()) == (1, 0)


def test_etapa_exige_medicao_e_entra_no_painel(cliente):
    assert cliente.post("/api/etapa", json={"anon_id": "aparelho-1", "etapa": "carrinho"}).status_code == 403
    aceitar(cliente, "aparelho-1", juncao=False)
    cliente.post("/api/evento", json={"anon_id": "aparelho-1", "tipo": "visita", "utm_source": "google", "utm_medium": "cpc"})
    assert cliente.post("/api/etapa", json={"anon_id": "aparelho-1", "etapa": "carrinho"}).status_code == 200
    assert cliente.post("/api/etapa", json={"anon_id": "aparelho-1", "etapa": "outra"}).status_code == 422
    cliente.post("/api/evento", json={"anon_id": "aparelho-1", "tipo": "conversao", "valor": 10})
    f = cliente.get("/api/painel", headers=ADMIN).json()["funil"]
    assert f["por_canal"]["Busca paga"] == {"visita": 1, "login": 0, "carrinho": 1, "compra": 1}
