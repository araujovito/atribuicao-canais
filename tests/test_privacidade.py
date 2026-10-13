import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from app.banco import conectar
from app.privacidade import aplicar_retencao, confirmar_exclusao, excluir_titular, pedir_exclusao, pseudonimo
from app.tempo import texto

CHAVE = b"chave-de-teste"
AGORA = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def con():
    return conectar(":memory:")


def evento(con, anon, pessoa=None, momento=AGORA):
    con.execute(
        "INSERT INTO eventos (anon_id, pessoa_id, tipo, momento) VALUES (?, ?, 'visita', ?)",
        (anon, pessoa, texto(momento)),
    )


def vinculo(con, anon, pessoa, momento=AGORA):
    con.execute("INSERT INTO vinculos VALUES (?, ?, ?)", (anon, pessoa, texto(momento)))


def contar(con, tabela="eventos"):
    return con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]


def test_pseudonimo_estavel_e_normalizado():
    assert pseudonimo(" Ana@Exemplo.com ", CHAVE) == pseudonimo("ana@exemplo.com", CHAVE)


def test_pseudonimo_depende_da_chave():
    # Sem a chave, não dá para refazer o identificador a partir de uma lista de e-mails.
    assert pseudonimo("ana@exemplo.com", CHAVE) != pseudonimo("ana@exemplo.com", b"outra")
    assert pseudonimo("ana@exemplo.com", CHAVE) != hashlib.sha256(b"ana@exemplo.com").hexdigest()


def test_nao_normaliza_alem_do_seguro():
    # "a.na" e "ana" são a mesma caixa no Gmail, mas não em outros provedores.
    assert pseudonimo("a.na@exemplo.com", CHAVE) != pseudonimo("ana@exemplo.com", CHAVE)


def test_exclusao_apaga_aparelho_exclusivo(con):
    ana = pseudonimo("ana@exemplo.com", CHAVE)
    vinculo(con, "celular-ana", ana)
    evento(con, "celular-ana")  # anônimo, antes do login
    evento(con, "celular-ana", ana)
    evento(con, "outro")
    r = excluir_titular(con, "ana@exemplo.com", CHAVE)
    assert r == {"eventos_identificados": 1, "eventos_anonimos": 1, "vinculos": 1}
    assert contar(con) == 1


def test_exclusao_preserva_eventos_anonimos_de_aparelho_compartilhado(con):
    ana, bruno = pseudonimo("ana@exemplo.com", CHAVE), pseudonimo("bruno@exemplo.com", CHAVE)
    vinculo(con, "pc-familia", ana)
    vinculo(con, "pc-familia", bruno)
    evento(con, "pc-familia")  # pode ser de qualquer um dos dois
    evento(con, "pc-familia", bruno)
    excluir_titular(con, "ana@exemplo.com", CHAVE)
    assert contar(con) == 2
    assert contar(con, "vinculos") == 1


def test_retencao(con):
    evento(con, "velho", momento=AGORA - timedelta(days=400))
    evento(con, "novo", momento=AGORA - timedelta(days=10))
    vinculo(con, "velho", "p", momento=AGORA - timedelta(days=400))
    for anon in ("velho", "novo"):
        con.execute(
            "INSERT INTO consentimentos (anon_id, versao, aceito, momento) VALUES (?, 'v1', 1, ?)",
            (anon, texto(AGORA - timedelta(days=400))),
        )
    assert aplicar_retencao(con, agora=AGORA) == 1
    assert contar(con) == 1 and contar(con, "vinculos") == 0
    # O consentimento de "novo" fica: ainda há evento coletado com base nele.
    assert [r[0] for r in con.execute("SELECT anon_id FROM consentimentos")] == ["novo"]


def test_codigo_vence_em_15_minutos(con):
    codigo = pedir_exclusao(con, "ana@exemplo.com", agora=AGORA, chave_hmac=CHAVE)
    depois = AGORA + timedelta(minutes=16)
    assert confirmar_exclusao(con, "ana@exemplo.com", codigo, agora=depois, chave_hmac=CHAVE) is None


def test_cinco_tentativas_erradas_queimam_o_codigo(con):
    codigo = pedir_exclusao(con, "ana@exemplo.com", agora=AGORA, chave_hmac=CHAVE)
    errado = "000000" if codigo != "000000" else "111111"
    for _ in range(5):
        assert confirmar_exclusao(con, "ana@exemplo.com", errado, agora=AGORA, chave_hmac=CHAVE) is None
    assert confirmar_exclusao(con, "ana@exemplo.com", codigo, agora=AGORA, chave_hmac=CHAVE) is None


def test_codigo_nao_fica_gravado(con):
    codigo = pedir_exclusao(con, "ana@exemplo.com", agora=AGORA, chave_hmac=CHAVE)
    assert codigo not in str([tuple(r) for r in con.execute("SELECT * FROM pedidos_exclusao")])
