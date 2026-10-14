"""API de coleta e de análise.

Rotas:
    POST   /api/consentimento   registra o banner: medição e junção, cada uma à parte
    POST   /api/evento          visita de entrada ou conversão; exige consentimento
    POST   /api/identificar     login/formulário: liga o aparelho ao pseudônimo
    GET    /api/painel          atribuição por modelo, com e sem junção [admin]
    POST   /api/titular/pedido  pede exclusão: envia código ao e-mail (LGPD art. 18)
    DELETE /api/titular         confirma a exclusão com o código
    DELETE /api/admin/titular   exclusão feita pelo atendimento [admin]
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
import threading
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import correio, privacidade, tempo
from app.acesso import exigir_admin
from app.limite import limitar
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

# CORS: o rastreador pode morar no site da loja (loja.com.br) e mandar os
# eventos para este serviço em outro domínio. Só as origens listadas em
# ATRIBUICAO_ORIGENS (separadas por vírgula) podem; lista vazia = só o mesmo
# domínio. "*" não é aceito de propósito: qualquer site poderia injetar
# eventos em nome dos seus visitantes.
# allow_headers só tem Content-Type: um site de fora não consegue mandar o
# cabeçalho Authorization, então as rotas de admin seguem só no mesmo domínio.
ORIGENS = [o.strip() for o in os.environ.get("ATRIBUICAO_ORIGENS", "").split(",") if o.strip() and o.strip() != "*"]
if ORIGENS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ORIGENS,
        allow_methods=["POST", "DELETE"],
        allow_headers=["Content-Type"],
        allow_credentials=False,
        max_age=600,
    )


def agora() -> str:
    return tempo.texto(tempo.agora())


def classe_aparelho(user_agent: str) -> str:
    ua = user_agent.lower()
    return "celular" if any(k in ua for k in ("mobi", "android", "iphone")) else "computador"


def consentimento(con: sqlite3.Connection, anon_id: str) -> tuple[bool, bool]:
    """(medição, junção) segundo o registro mais recente do aparelho."""
    linha = con.execute(
        "SELECT aceito, juncao FROM consentimentos WHERE anon_id = ? ORDER BY id DESC LIMIT 1", (anon_id,)
    ).fetchone()
    if not linha:
        return False, False
    # Junção sem medição não existe: sem a coleta, não há o que juntar.
    return bool(linha["aceito"]), bool(linha["aceito"] and linha["juncao"])


# UUID do navegador (ou o identificador de reserva do rastreio.js): letras,
# dígitos e hífen. Recusa texto arbitrário que alguém tente usar como id.
ANON_ID = r"^[A-Za-z0-9-]{8,64}$"


class Consentimento(BaseModel):
    anon_id: str = Field(pattern=ANON_ID)
    aceito: bool  # medição
    juncao: bool = False  # ligar e-mail ao aparelho; precisa ser marcada à parte
    versao: str = Field(max_length=20)


class Evento(BaseModel):
    anon_id: str = Field(pattern=ANON_ID)
    tipo: str = Field(pattern="^(visita|conversao)$")
    host: str | None = None
    referrer: str | None = None
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    gclid: str | None = None
    valor: float = Field(default=0, ge=0, le=1_000_000)
    email: str | None = Field(default=None, max_length=254)


class Identificacao(BaseModel):
    anon_id: str = Field(pattern=ANON_ID)
    email: str = Field(min_length=3, max_length=254)


class Titular(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class Confirmacao(Titular):
    codigo: str = Field(pattern=r"^\s*\d{6}\s*$")


def vincular(con: sqlite3.Connection, anon_id: str, email: str) -> str:
    pid = privacidade.pseudonimo(email)
    with con:
        con.execute("INSERT OR IGNORE INTO vinculos VALUES (?, ?, ?)", (anon_id, pid, agora()))
    return pid


@app.post("/api/consentimento", dependencies=[Depends(limitar("consentimento", 20, 60))])
def registrar_consentimento(c: Consentimento, con: sqlite3.Connection = Banco):
    juncao = c.aceito and c.juncao
    with con:
        con.execute(
            "INSERT INTO consentimentos (anon_id, versao, aceito, juncao, momento) VALUES (?, ?, ?, ?, ?)",
            (c.anon_id, c.versao, int(c.aceito), int(juncao), agora()),
        )
        if not juncao:
            # Retirar a junção desfaz as ligações deste aparelho daqui em
            # diante: o vínculo some e os eventos dele voltam a ser anônimos.
            con.execute("DELETE FROM vinculos WHERE anon_id = ?", (c.anon_id,))
            con.execute("UPDATE eventos SET pessoa_id = NULL WHERE anon_id = ? AND pessoa_id IS NOT NULL",
                        (c.anon_id,))
    return {"ok": True}


@app.post("/api/evento", dependencies=[Depends(limitar("evento", 60, 60))])
def registrar_evento(ev: Evento, request: Request, con: sqlite3.Connection = Banco):
    medicao, juncao = consentimento(con, ev.anon_id)
    if not medicao:
        raise HTTPException(403, "sem consentimento registrado para este aparelho")
    canal = None
    if ev.tipo == "visita":
        canal = classificar(ev.utm_source, ev.utm_medium, ev.referrer, ev.host, ev.gclid)
    # O e-mail da compra só liga o aparelho à pessoa com a junção autorizada.
    pessoa_id = vincular(con, ev.anon_id, ev.email) if ev.email and juncao else None
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


@app.post("/api/identificar", dependencies=[Depends(limitar("identificar", 20, 60))])
def identificar(i: Identificacao, con: sqlite3.Connection = Banco):
    if not consentimento(con, i.anon_id)[1]:
        raise HTTPException(403, "sem consentimento para junção entre aparelhos")
    vincular(con, i.anon_id, i.email)
    return {"ok": True}


def _serializar(resultados) -> dict:
    return {
        m: {"nome": NOMES[m], "conversoes": r.conversoes, "receita": r.receita}
        for m, r in resultados.items()
    }


@app.get("/api/painel", dependencies=Admin)
def painel(janela_dias: int = Query(JANELA_DIAS, ge=1, le=365), con: sqlite3.Connection = Banco):
    chave = (janela_dias, versao_dos_dados(con))
    with _trava_cache:
        if chave in _cache_painel:
            _cache_painel.move_to_end(chave)
            return _cache_painel[chave]
    resultado = calcular_painel(con, janela_dias)
    with _trava_cache:
        _cache_painel[chave] = resultado
        while len(_cache_painel) > 8:
            _cache_painel.popitem(last=False)
    return resultado


# Cache do painel. Recalcular monta as jornadas duas vezes (com e sem junção)
# e roda os seis modelos em cada uma; com dezenas de milhares de eventos são
# segundos por acesso, e o resultado só muda quando os dados mudam.
_cache_painel: OrderedDict = OrderedDict()
_trava_cache = threading.Lock()


def versao_dos_dados(con: sqlite3.Connection) -> int:
    """Contador mantido por triggers: muda a cada escrita em eventos e vínculos.

    Descartado: assinatura por contagem, maior id e soma dos ids. Sem
    AUTOINCREMENT, o SQLite reaproveita o maior id quando a última linha é
    apagada, e "apaga a última, insere uma" deixaria a assinatura igual.
    """
    return con.execute("SELECT n FROM versao").fetchone()[0]


def calcular_painel(con: sqlite3.Connection, janela_dias: int) -> dict:
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


@app.post("/api/titular/pedido", dependencies=[Depends(limitar("pedido_exclusao", 5, 3600))])
def pedir_exclusao(t: Titular, con: sqlite3.Connection = Banco):
    codigo = privacidade.pedir_exclusao(con, t.email)
    correio.enviar(t.email, "Código para excluir seus dados",
                   f"Use o código {codigo} em até {privacidade.CODIGO_MINUTOS} minutos.")
    # Mesma resposta exista ou não dado ligado ao e-mail.
    return {"ok": True, "mensagem": "Se houver dados ligados a este e-mail, enviamos um código."}


@app.delete("/api/titular", dependencies=[Depends(limitar("confirma_exclusao", 10, 3600))])
def excluir(c: Confirmacao, con: sqlite3.Connection = Banco):
    apagados = privacidade.confirmar_exclusao(con, c.email, c.codigo)
    if apagados is None:
        raise HTTPException(403, "código inválido, vencido ou com tentativas esgotadas")
    return {"ok": True, "apagados": apagados}


@app.delete("/api/admin/titular", dependencies=Admin)
def excluir_pelo_atendimento(t: Titular, con: sqlite3.Connection = Banco):
    """Para pedidos que chegam por outro canal (SAC, e-mail ao encarregado),
    em que a identidade já foi conferida por quem atende."""
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


@app.get("/privacidade")
def pagina_privacidade():
    return FileResponse(WEB / "privacidade.html")


@app.get("/loja")
def pagina_loja():
    return FileResponse(WEB / "loja.html")


app.mount("/web", StaticFiles(directory=WEB), name="web")
