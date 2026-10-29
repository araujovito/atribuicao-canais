import os
import subprocess
import sys

CODIGO = r"""
import os, tempfile, pathlib
os.environ.pop("DATABASE_URL", None)
os.environ["ATRIBUICAO_BANCO"] = str(pathlib.Path(tempfile.mkdtemp()) / "d.db")
os.environ["ATRIBUICAO_GERAR_DEMO"] = "1"
os.environ["ATRIBUICAO_PESSOAS_DEMO"] = "100"
os.environ["ATRIBUICAO_CHAVE_HMAC"] = "x"
from fastapi.testclient import TestClient
from app.main import app, CAMINHO_BANCO
from app.banco import conectar
with TestClient(app):
    pass
n = conectar(CAMINHO_BANCO).execute("SELECT COUNT(*) FROM eventos").fetchone()[0]
with TestClient(app):  # segunda subida: banco já tem dados, não gera de novo
    pass
assert conectar(CAMINHO_BANCO).execute("SELECT COUNT(*) FROM eventos").fetchone()[0] == n
print("ok", n)
"""


def test_demo_gera_dados_so_com_banco_vazio():
    r = subprocess.run([sys.executable, "-c", CODIGO], capture_output=True, text=True,
                       cwd=os.path.dirname(os.path.dirname(__file__)))
    assert r.stdout.startswith("ok") and int(r.stdout.split()[1]) > 0, r.stderr[-2000:]
