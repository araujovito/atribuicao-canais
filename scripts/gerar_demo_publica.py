"""Gera um retrato agregado e exclusivamente sintético para o painel público."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from app.banco import conectar
from scripts.gerar_dados import gerar


def main() -> None:
    # Nunca usa DATABASE_URL, nem lê os dados da aplicação ou credenciais reais.
    os.environ["ATRIBUICAO_CHAVE_HMAC"] = "somente-dados-ficticios-da-demonstracao"
    from app.main import FONTES, calcular_painel

    with tempfile.TemporaryDirectory() as pasta:
        banco = Path(pasta) / "demo.db"
        gerar(banco, 2000, 42, datetime(2026, 10, 13, 12, tzinfo=timezone.utc))
        con = conectar(banco)
        try:
            resultado = calcular_painel(con, 30)
        finally:
            con.close()
    resultado["fonte"] = {**FONTES["ficticio"], "nome": "Demonstração: dados fictícios"}
    destino = Path(__file__).resolve().parent.parent / "web" / "demo.json"
    destino.write_text(json.dumps(resultado, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Demonstração gerada: {resultado['resumo']['conversoes']} conversões fictícias")


if __name__ == "__main__":
    main()
