import os
import subprocess
import sys

# O middleware é configurado no import; roda num processo próprio para não
# contaminar o app dos outros testes.
CODIGO = r"""
import os, tempfile, pathlib
os.environ.pop("DATABASE_URL", None)
os.environ["ATRIBUICAO_BANCO"] = str(pathlib.Path(tempfile.mkdtemp()) / "c.db")
os.environ["ATRIBUICAO_ORIGENS"] = "https://loja.exemplo, *"
os.environ["ATRIBUICAO_CHAVE_HMAC"] = "x"
from fastapi.testclient import TestClient
from app.main import app
c = TestClient(app)
def pre(origem, cabecalhos="content-type"):
    return c.options("/api/evento", headers={"origin": origem, "access-control-request-method": "POST",
                                             "access-control-request-headers": cabecalhos})
ok = pre("https://loja.exemplo")
assert ok.headers.get("access-control-allow-origin") == "https://loja.exemplo", ok.headers
assert "access-control-allow-origin" not in pre("https://intruso.exemplo").headers
assert pre("https://loja.exemplo", "authorization").status_code == 400  # admin não sai do domínio
print("ok")
"""


def test_cors_so_para_origens_listadas():
    r = subprocess.run([sys.executable, "-c", CODIGO], capture_output=True, text=True,
                       cwd=os.path.dirname(os.path.dirname(__file__)))
    assert r.stdout.strip().endswith("ok"), r.stderr[-2000:]
