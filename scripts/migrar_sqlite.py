"""Copia um SQLite existente para um esquema PostgreSQL vazio, sem alterar a origem."""
from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path

from psycopg import sql

from app.postgres import Conexao

TABELAS = ("eventos", "vinculos", "consentimentos", "etapas", "experimentos", "verdade", "pedidos_exclusao")
IDENTIDADES = ("eventos", "consentimentos", "etapas")
CHAVES = {
    "eventos": ("id",), "vinculos": ("anon_id", "pessoa_id"), "consentimentos": ("id",),
    "etapas": ("id",), "experimentos": ("anon_id", "canal"), "verdade": ("canal",),
    "pedidos_exclusao": ("pessoa_id",),
}


def migrar(origem: Path, url: str, esquema: str = "public") -> dict[str, int]:
    if not origem.is_file():
        raise ValueError("O arquivo SQLite de origem não existe")
    fonte = sqlite3.connect(f"{origem.resolve().as_uri()}?mode=ro", uri=True)
    destino = None
    try:
        fonte.execute("BEGIN")  # snapshot consistente durante toda a leitura
        destino = Conexao(url, schema=esquema)
        contagens = {}
        with destino:
            destino.raw.execute(sql.SQL("LOCK TABLE {} IN ACCESS EXCLUSIVE MODE").format(
                sql.SQL(", ").join(map(sql.Identifier, TABELAS))))
            for tabela in TABELAS:
                if destino.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]:
                    raise ValueError(f"Destino não está vazio: {tabela}")
            existentes = {r[0] for r in fonte.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            for tabela in TABELAS:
                if tabela not in existentes:
                    contagens[tabela] = 0
                    continue
                colunas = [r[1] for r in fonte.execute(f"PRAGMA table_info({tabela})")]
                linhas = fonte.execute(f"SELECT * FROM {tabela}")
                comando = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                    sql.Identifier(tabela), sql.SQL(", ").join(map(sql.Identifier, colunas)),
                    sql.SQL(", ").join(sql.Placeholder() for _ in colunas))
                cursor = destino.raw.cursor()
                quantidade = 0
                while lote := linhas.fetchmany(1000):
                    cursor.executemany(comando, lote)
                    quantidade += len(lote)
                total = destino.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
                if total != quantidade:
                    raise RuntimeError(f"Contagem divergente em {tabela}")
                ordem_fonte = ", ".join(f'{c} COLLATE BINARY' if c != "id" else c for c in CHAVES[tabela])
                ordem_destino = sql.SQL(", ").join(
                    sql.SQL('{} COLLATE "C"').format(sql.Identifier(c)) if c != "id" else sql.Identifier(c)
                    for c in CHAVES[tabela]
                )
                esperado = fonte.execute(f"SELECT * FROM {tabela} ORDER BY {ordem_fonte}")
                verificado = destino.raw.execute(sql.SQL("SELECT {} FROM {} ORDER BY {}").format(
                    sql.SQL(", ").join(map(sql.Identifier, colunas)), sql.Identifier(tabela), ordem_destino))
                while lote := esperado.fetchmany(1000):
                    recebido = verificado.fetchmany(len(lote))
                    if lote != [tuple(linha.values()) for linha in recebido]:
                        raise RuntimeError(f"Conteúdo divergente em {tabela}")
                contagens[tabela] = total
            for tabela in IDENTIDADES:
                destino.raw.execute(sql.SQL("SELECT setval(pg_get_serial_sequence(%s, 'id'), "
                                            "COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM {}")
                                    .format(sql.Identifier(tabela)), (f"{esquema}.{tabela}",))
        return contagens
    finally:
        fonte.close()
        if destino:
            destino.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("origem", type=Path)
    parser.add_argument("--esquema", choices=("public", "ga4"), default="public")
    args = parser.parse_args()
    url = os.environ.get("DATABASE_URL")
    if not url:
        parser.error("defina DATABASE_URL")
    resultado = migrar(args.origem, url, args.esquema)
    print("Migração concluída: " + ", ".join(f"{t}={n}" for t, n in resultado.items()))


if __name__ == "__main__":
    main()
