"""API de coleta e de análise.

Rotas:
    POST   /api/consentimento   registra o sim/não do banner (com versão do texto)
    POST   /api/evento          visita de entrada ou conversão; exige consentimento
    POST   /api/identificar     login/formulário: liga o aparelho ao pseudônimo
    GET    /api/painel          atribuição por modelo, com e sem junção [admin]
    DELETE /api/titular         exclusão a pedido (LGPD art. 18)
    POST   /api/retencao        aplica o prazo de retenção, mínimo 30 dias [admin]
    GET    /, /loja             painel e loja de demonstração

[admin] = exige `Authorization: Bearer <token>`, ver app/acesso.py.

O servidor confere o consentimento de novo, mesmo que o rastreador só envie
depois do "sim": o navegador é do usuário, e qualquer um pode mandar um POST
na mão. Sem consentimento registrado, o evento é recusado e não é gravado.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import privacidade, tempo
from app.acesso import exigir_admin
from app.atribuicao import NOMES, comparar
from app.banco import conectar
from app.canais import CANAIS, classificar
from app.jornadas import JANELA_DIAS, montar

RAIZ = Path(__file__).resolve().parent.parent
WEB = RAIZ / "web"
CAMINHO_BANCO = os.environ.get("ATRIBUICAO_BANCO", str(RAIZ / "atribuicao.db"))


def banco() -> Iterator[sqlite3.Connection]:
    """Uma conexão por requisição, fechada no fim.

    FastAPI roda as rotas síncronas num pool de threads. Uma conexão única
    compartilhada (check_same_thread=False) deixa duas requisições usarem o
    mesmo cursor ao mesmo tempo, e transações de uma vazam para a outra.
    Abrir uma conexão SQLite custa microssegundos; não vale o risco.
    """
    con = conectar(CAMINHO_BANCO, criar=False)
    try:
        yield con
    finally:
        con.close()


Banco = Depends(banco)
Admin = [Depends(exigir_admin)]


@asynccontextmanager
async def ciclo(_: FastAPI):
    con = conectar(CAMINHO_BANCO)  # cria o esquema uma vez, na subida
    privacidade.aplicar_retencao(con)
    con.close()
    yield


app = FastAPI(title="Atribuição de canais", lifespan=ciclo)


def agora() -> str:
    return tempo.texto(tempo.agora())


def classe_aparelho(user_agent: str) -> str:
    ua = user_agent.lower()
    return "celular" if any(k in ua for k in ("mobi", "android", "iphone")) else "computador"


def tem_consentimento(con: sqlite3.Connection, anon_id: str) -> bool:
    linha = con.execute(
        "SELECT aceito FROM consentimentos WHERE anon_id = ? ORDER BY id DESC LIMIT 1", (anon_id,)
    ).fetchone()
    return bool(linha and linha["aceito"])


class Consentimento(BaseModel):
    anon_id: str = Field(min_length=8, max_length=64)
    aceito: bool
    versao: str = Field(max_length=20)


class Evento(BaseModel):
    anon_id: str = Field(min_length=8, max_length=64)
    tipo: str = Field(pattern="^(visita|conversao)$")
    host: str | None = None
    referrer: str | None = None
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    gclid: str | None = None
    valor: float = Field(default=0, ge=0)
    email: str | None = Field(default=None, max_length=254)


class Identificacao(BaseModel):
    anon_id: str = Field(min_length=8, max_length=64)
    email: str = Field(min_length=3, max_length=254)


class Titular(BaseModel):
    email: str = Field(min_length=3, max_length=254)


def vincular(con: sqlite3.Connection, anon_id: str, email: str) -> str:
    pid = privacidade.pseudonimo(email)
    with con:
        con.execute("INSERT OR IGNORE INTO vinculos VALUES (?, ?, ?)", (anon_id, pid, agora()))
    return pid


@app.post("/api/consentimento")
def registrar_consentimento(c: Consentimento, con: sqlite3.Connection = Banco):
    with con:
        con.execute(
            "INSERT INTO consentimentos (anon_id, versao, aceito, momento) VALUES (?, ?, ?, ?)",
            (c.anon_id, c.versao, int(c.aceito), agora()),
        )
    return {"ok": True}


@app.post("/api/evento")
def registrar_evento(ev: Evento, request: Request, con: sqlite3.Connection = Banco):
    if not tem_consentimento(con, ev.anon_id):
        raise HTTPException(403, "sem consentimento registrado para este aparelho")
    canal = None
    if ev.tipo == "visita":
        canal = classificar(ev.utm_source, ev.utm_medium, ev.referrer, ev.host, ev.gclid)
    pessoa_id = vincular(con, ev.anon_id, ev.email) if ev.email else None
    with con:
        con.execute(
            """INSERT INTO eventos (anon_id, pessoa_id, tipo, canal, utm_source, utm_medium,
                   utm_campaign, referrer_host, aparelho, valor, momento)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ev.anon_id, pessoa_id, ev.tipo, canal, ev.utm_source, ev.utm_medium, ev.utm_campaign,
                urlparse(ev.referrer).hostname if ev.referrer else None,
                classe_aparelho(request.headers.get("user-agent", "")),
                ev.valor if ev.tipo == "conversao" else 0, agora(),
            ),
        )
    return {"ok": True, "canal": canal}


@app.post("/api/identificar")
def identificar(i: Identificacao, con: sqlite3.Connection = Banco):
    if not tem_consentimento(con, i.anon_id):
        raise HTTPException(403, "sem consentimento registrado para este aparelho")
    vincular(con, i.anon_id, i.email)
    return {"ok": True}


def _serializar(resultados) -> dict:
    return {
        m: {"nome": NOMES[m], "conversoes": r.conversoes, "receita": r.receita}
        for m, r in resultados.items()
    }


@app.get("/api/painel", dependencies=Admin)
def painel(janela_dias: int = JANELA_DIAS, con: sqlite3.Connection = Banco):
    com = montar(con, janela_dias)
    sem = montar(con, janela_dias, juntar=False)
    visitas = con.execute(
        "SELECT canal, aparelho, COUNT(*) n FROM eventos WHERE tipo = 'visita' AND canal IS NOT NULL GROUP BY 1, 2"
    ).fetchall()
    convertidas = [j for j in com.jornadas if j.converteu]
    return {
        "canais": list(CANAIS),
        "modelos": _serializar(comparar(com.jornadas)),
        "sem_juncao": _serializar(comparar(sem.jornadas)),
        "visitas": [dict(v) for v in visitas],
        "resumo": {
            "janela_dias": janela_dias,
            "aparelhos": com.aparelhos,
            "pessoas_identificadas": com.pessoas_identificadas,
            "aparelhos_ambiguos": com.aparelhos_ambiguos,
            "conversoes": len(convertidas),
            "receita": sum(j.valor for j in convertidas),
            "conversoes_entre_aparelhos": com.conversoes_entre_aparelhos,
            "jornadas_sem_conversao": len(com.jornadas) - len(convertidas),
        },
    }


@app.delete("/api/titular")
def excluir(t: Titular, con: sqlite3.Connection = Banco):
    return {"ok": True, "apagados": privacidade.excluir_titular(con, t.email)}


@app.post("/api/retencao", dependencies=Admin)
def retencao(
    # Piso de 30 dias: o prazo existe para expirar dado velho, não para
    # esvaziar o banco. Apagar tudo, se um dia for preciso, é operação
    # deliberada fora da API, não um parâmetro.
    dias: int = Query(privacidade.RETENCAO_DIAS, ge=30),
    con: sqlite3.Connection = Banco,
):
    return {"ok": True, "eventos_apagados": privacidade.aplicar_retencao(con, dias)}


@app.get("/")
def pagina_painel():
    return FileResponse(WEB / "index.html")


@app.get("/loja")
def pagina_loja():
    return FileResponse(WEB / "loja.html")


app.mount("/web", StaticFiles(directory=WEB), name="web")
