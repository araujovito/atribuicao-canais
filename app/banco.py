"""Esquema SQLite do protótipo.

Minimização (LGPD art. 6º, III) decidida no esquema, não na boa vontade de
quem consulta:
- e-mail nunca é gravado; só o HMAC dele (`pessoa_id`), ver app/privacidade.py;
- do referrer guarda-se só o host. A URL completa pode carregar termo de
  busca, e-mail em parâmetro de formulário ou token de sessão de outro site;
- do navegador guarda-se só a classe do aparelho (celular/computador), não o
  User-Agent inteiro, e IP não é gravado.

Em produção isto seria Postgres ou um banco analítico atrás de uma fila de
eventos; para demonstrar a lógica, SQLite basta e roda sem servidor.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS eventos (
    id            INTEGER PRIMARY KEY,
    anon_id       TEXT NOT NULL,
    pessoa_id     TEXT,
    tipo          TEXT NOT NULL CHECK (tipo IN ('visita', 'conversao')),
    canal         TEXT,
    utm_source    TEXT,
    utm_medium    TEXT,
    utm_campaign  TEXT,
    referrer_host TEXT,
    aparelho      TEXT,
    valor         REAL NOT NULL DEFAULT 0,
    momento       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS eventos_anon ON eventos (anon_id);
CREATE INDEX IF NOT EXISTS eventos_pessoa ON eventos (pessoa_id);
CREATE INDEX IF NOT EXISTS eventos_momento ON eventos (momento);

CREATE TABLE IF NOT EXISTS vinculos (
    anon_id   TEXT NOT NULL,
    pessoa_id TEXT NOT NULL,
    momento   TEXT NOT NULL,
    PRIMARY KEY (anon_id, pessoa_id)
);

-- Registro do consentimento: a LGPD (art. 8º, §2º) põe no controlador o ônus
-- de provar que o consentimento foi obtido. Guarda-se a versão do texto do
-- banner que a pessoa viu.
CREATE TABLE IF NOT EXISTS consentimentos (
    id      INTEGER PRIMARY KEY,
    anon_id TEXT NOT NULL,
    versao  TEXT NOT NULL,
    aceito  INTEGER NOT NULL,
    momento TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS consentimentos_anon ON consentimentos (anon_id);
"""


def conectar(caminho: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(caminho, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(ESQUEMA)
    return con
