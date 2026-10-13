from datetime import datetime

from scripts.gerar_dados import gerar

from app.banco import conectar
from app.jornadas import montar

HOJE = datetime(2026, 10, 13, 12, 0)


def test_reproduzivel_e_sem_dado_real(tmp_path):
    a = gerar(tmp_path / "a.db", 300, 7, HOJE)
    b = gerar(tmp_path / "b.db", 300, 7, HOJE)
    assert a == b
    con = conectar(tmp_path / "a.db")
    # Só pseudônimos: nenhum e-mail no banco.
    assert not con.execute("SELECT 1 FROM eventos WHERE pessoa_id LIKE '%@%'").fetchone()
    assert con.execute("SELECT MAX(momento) FROM eventos").fetchone()[0] <= HOJE.isoformat()


def test_ha_compras_entre_aparelhos_e_juncao_recupera_parte(tmp_path):
    stats = gerar(tmp_path / "d.db", 1000, 42, HOJE)
    m = montar(conectar(tmp_path / "d.db"))
    assert stats["compras_entre_aparelhos"] > 0
    # Só quem fez login no celular é juntado: recupera parte, não tudo.
    assert 0 < m.conversoes_entre_aparelhos <= stats["compras_entre_aparelhos"]
