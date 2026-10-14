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
-- banner que a pessoa viu e a resposta por finalidade (art. 8º, §4º:
-- autorização genérica é nula):
--   aceito = medição (canal de origem e compras, por aparelho);
--   juncao = ligar o e-mail ao aparelho para juntar celular e computador.
CREATE TABLE IF NOT EXISTS consentimentos (
    id      INTEGER PRIMARY KEY,
    anon_id TEXT NOT NULL,
    versao  TEXT NOT NULL,
    aceito  INTEGER NOT NULL,
    juncao  INTEGER NOT NULL DEFAULT 0,
    momento TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS consentimentos_anon ON consentimentos (anon_id);

-- Etapas do funil que não são visita nem compra (login, carrinho). Ficam em
-- tabela própria porque não entram na atribuição, só no funil.
CREATE TABLE IF NOT EXISTS etapas (
    id      INTEGER PRIMARY KEY,
    anon_id TEXT NOT NULL,
    etapa   TEXT NOT NULL CHECK (etapa IN ('login', 'carrinho')),
    momento TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS etapas_anon ON etapas (anon_id);

-- Teste de incrementalidade (ghost ads): quem seria exposto ao anúncio de um
-- canal é sorteado para tratamento (vê o anúncio) ou controle (não vê, mas o
-- sorteio fica registrado). Vem da plataforma de anúncios, que é quem sabe
-- quem seria exposto; aqui, do gerador de dados.
CREATE TABLE IF NOT EXISTS experimentos (
    anon_id TEXT NOT NULL,
    canal   TEXT NOT NULL,
    grupo   TEXT NOT NULL CHECK (grupo IN ('tratamento', 'controle')),
    momento TEXT NOT NULL,
    PRIMARY KEY (anon_id, canal)
);

-- Versão dos dados: um contador que toda escrita em eventos e vínculos
-- incrementa. O cache do painel compara este número (ver app/main.py).
CREATE TABLE IF NOT EXISTS versao (n INTEGER NOT NULL);
INSERT INTO versao SELECT 0 WHERE NOT EXISTS (SELECT 1 FROM versao);
CREATE TRIGGER IF NOT EXISTS versao_ev_i AFTER INSERT ON eventos BEGIN UPDATE versao SET n = n + 1; END;
CREATE TRIGGER IF NOT EXISTS versao_ev_d AFTER DELETE ON eventos BEGIN UPDATE versao SET n = n + 1; END;
CREATE TRIGGER IF NOT EXISTS versao_ev_u AFTER UPDATE ON eventos BEGIN UPDATE versao SET n = n + 1; END;
CREATE TRIGGER IF NOT EXISTS versao_vi_i AFTER INSERT ON vinculos BEGIN UPDATE versao SET n = n + 1; END;
CREATE TRIGGER IF NOT EXISTS versao_vi_d AFTER DELETE ON vinculos BEGIN UPDATE versao SET n = n + 1; END;
CREATE TRIGGER IF NOT EXISTS versao_et_i AFTER INSERT ON etapas BEGIN UPDATE versao SET n = n + 1; END;
CREATE TRIGGER IF NOT EXISTS versao_et_d AFTER DELETE ON etapas BEGIN UPDATE versao SET n = n + 1; END;
CREATE TRIGGER IF NOT EXISTS versao_ex_i AFTER INSERT ON experimentos BEGIN UPDATE versao SET n = n + 1; END;
CREATE TRIGGER IF NOT EXISTS versao_ex_d AFTER DELETE ON experimentos BEGIN UPDATE versao SET n = n + 1; END;

-- Pedido de exclusão aguardando confirmação pelo código enviado ao e-mail.
-- Guarda o HMAC do código, nunca o código; expira em 15 minutos e aceita
-- no máximo 5 tentativas.
CREATE TABLE IF NOT EXISTS pedidos_exclusao (
    pessoa_id   TEXT PRIMARY KEY,
    codigo_hash TEXT NOT NULL,
    expira      TEXT NOT NULL,
    tentativas  INTEGER NOT NULL DEFAULT 0
);
"""


def conectar(caminho: str | Path, criar: bool = True) -> sqlite3.Connection:
    """Abre o banco. `criar=False` pula o esquema (já criado na subida do servidor).

    WAL deixa leituras do painel rodarem enquanto a coleta grava; o timeout
    faz uma escrita esperar a outra até 5 s em vez de falhar na hora.

    check_same_thread=False não volta a compartilhar conexão: cada uma
    continua sendo de uma requisição só. O FastAPI é que abre a dependência
    numa thread do pool e roda a rota em outra, e a checagem padrão do
    sqlite3 recusaria isso.
    """
    con = sqlite3.connect(caminho, timeout=5, check_same_thread=False)
    con.row_factory = sqlite3.Row
    if str(caminho) != ":memory:":
        con.execute("PRAGMA journal_mode=WAL")
    if criar:
        con.executescript(ESQUEMA)
        _migrar(con)
    return con


def _migrar(con: sqlite3.Connection) -> None:
    """Colunas acrescentadas depois da primeira versão, para bancos já criados."""
    colunas = {r["name"] for r in con.execute("PRAGMA table_info(consentimentos)")}
    if "juncao" not in colunas:
        # Consentimento antigo (v1) era uma autorização só; não vale para a
        # junção, que agora é finalidade separada: entra como 0.
        con.execute("ALTER TABLE consentimentos ADD COLUMN juncao INTEGER NOT NULL DEFAULT 0")
