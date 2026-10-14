import csv
import io

from app.banco import conectar
from scripts.importar_ga4 import converter, gravar

# Formato que o `bq --format=csv` devolve para a consulta do importador.
CSV = """tipo,u,aparelho,ts,fonte,midia,campanha,receita
visita,u1,mobile,1604188800000000,google,cpc,BlackFriday_V1,
visita,u1,desktop,1604275200000000,shop.googlemerchandisestore.com,referral,(referral),
visita,u2,tablet,1604188800000000,<Other>,<Other>,<Other>,
visita,u3,desktop,1604188800000000,,,,
visita,u4,desktop,1604188800000000,(direct),(none),(direct),
carrinho,u1,desktop,1604275300000000,,,,
conversao,u1,desktop,1604275400000000,,,,45.5
conversao,u4,desktop,1604188900000000,,,,
"""


def test_converte_o_vocabulario_da_base_publica():
    eventos, etapas, stats = converter(csv.DictReader(io.StringIO(CSV)))
    canais = [(e[0], e[3]) for e in eventos if e[2] == "visita"]
    assert canais == [
        ("u1", "Busca paga"),
        ("u1", None),  # o próprio site: navegação interna, sem canal
        ("u2", "Não identificado"),  # anonimizado pelo Google
        ("u3", "Não identificado"),  # sessão sem origem registrada
        ("u4", "Direto"),
    ]
    assert stats == {"visitas": 5, "internas": 1, "sem_origem": 1, "compras": 2, "compras_sem_valor": 1, "carrinhos": 1}
    assert [e[8] for e in eventos][:3] == ["celular", "computador", "celular"]  # tablet conta como celular
    assert eventos[0][10] == "2020-11-01T00:00:00+00:00"
    assert [e[9] for e in eventos if e[2] == "conversao"] == [45.5, 0.0]
    assert etapas == [("u1", "carrinho", "2020-11-02T00:01:40+00:00")]


def test_grava_banco_completo(tmp_path):
    eventos, etapas, _ = converter(csv.DictReader(io.StringIO(CSV)))
    destino = tmp_path / "ga4.db"
    gravar(destino, eventos, etapas)
    con = conectar(destino)
    assert con.execute("SELECT COUNT(*) FROM eventos").fetchone()[0] == 7
    assert con.execute("SELECT COUNT(*) FROM vinculos").fetchone()[0] == 0  # base sem login
    assert not (tmp_path / "ga4.tmp").exists()
