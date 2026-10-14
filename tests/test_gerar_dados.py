from datetime import datetime, timezone

import pytest

from scripts.gerar_dados import BancoComDados, gerar

from app.banco import conectar
from app.jornadas import montar
from app.tempo import texto

HOJE = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


def test_reproduzivel_e_sem_dado_real(tmp_path):
    a = gerar(tmp_path / "a.db", 300, 7, HOJE)
    b = gerar(tmp_path / "b.db", 300, 7, HOJE)
    assert a == b
    con = conectar(tmp_path / "a.db")
    # Só pseudônimos: nenhum e-mail no banco.
    assert not con.execute("SELECT 1 FROM eventos WHERE pessoa_id LIKE '%@%'").fetchone()
    assert con.execute("SELECT MAX(momento) FROM eventos").fetchone()[0] <= texto(HOJE)


def test_ha_compras_entre_aparelhos_e_juncao_recupera_parte(tmp_path):
    stats = gerar(tmp_path / "d.db", 1000, 42, HOJE)
    m = montar(conectar(tmp_path / "d.db"))
    assert stats["compras_entre_aparelhos"] > 0
    # Só quem fez login no celular é juntado: recupera parte, não tudo.
    assert 0 < m.conversoes_entre_aparelhos <= stats["compras_entre_aparelhos"]


def test_nao_apaga_banco_com_dados_sem_pedir(tmp_path):
    caminho = tmp_path / "b.db"
    gerar(caminho, 50, 1, HOJE)
    antes = conectar(caminho).execute("SELECT COUNT(*) FROM eventos").fetchone()[0]
    with pytest.raises(BancoComDados):
        gerar(caminho, 10, 2, HOJE)
    assert conectar(caminho).execute("SELECT COUNT(*) FROM eventos").fetchone()[0] == antes
    gerar(caminho, 10, 2, HOJE, substituir=True)
    assert conectar(caminho).execute("SELECT COUNT(*) FROM eventos").fetchone()[0] != antes


def test_controle_nao_ve_o_canal_do_experimento(tmp_path):
    caminho = tmp_path / "e.db"
    gerar(caminho, 800, 3, HOJE)
    con = conectar(caminho)
    for canal in ("Display", "Social pago"):
        grupos = dict(con.execute("SELECT grupo, COUNT(*) FROM experimentos WHERE canal = ? GROUP BY 1", (canal,)).fetchall())
        assert grupos.get("controle") and grupos.get("tratamento")
        # Controle que "viu" o canal só pode ser computador compartilhado: outra
        # pessoa, no tratamento ou fora do teste, viu o anúncio no mesmo
        # aparelho. É a contaminação que existe em experimento real.
        vistos = con.execute(
            """SELECT DISTINCT e.anon_id FROM eventos e
               JOIN experimentos x ON x.anon_id = e.anon_id AND x.canal = e.canal
               WHERE x.grupo = 'controle'""").fetchall()
        for (anon,) in vistos:
            pessoas = con.execute("SELECT COUNT(*) FROM consentimentos WHERE anon_id = ?", (anon,)).fetchone()[0]
            assert pessoas > 1, (canal, anon)
