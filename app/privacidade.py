"""Pseudonimização, exclusão a pedido do titular e retenção.

Pseudonimização por HMAC-SHA256 com chave secreta, e não SHA-256 puro: e-mail
tem pouca entropia, e um hash sem chave se reverte testando listas de
e-mails vazados. Com HMAC, sem a chave o identificador não volta a ser
e-mail. Ainda é dado pessoal para a LGPD (é pseudonimizado, não anonimizado,
porque quem tem a chave refaz a ligação), e por isso existe a exclusão.

A chave vem da variável de ambiente ATRIBUICAO_CHAVE_HMAC. Sem ela, o
protótipo usa uma chave de desenvolvimento e avisa — aceitável para dados
fictícios, nunca para produção. Trocar a chave desliga todos os vínculos
antigos (os mesmos e-mails passam a gerar outros identificadores).

Retenção: a LGPD não fixa prazo, só exige que o dado seja eliminado quando a
finalidade acabar (art. 15 e 16). O padrão de 13 meses segue a referência da
CNIL francesa para dados de medição de audiência: cobre a comparação de um
mês com o mesmo mês do ano anterior.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import warnings
from datetime import datetime, timedelta

from app import tempo

CHAVE_DEV = "chave-de-desenvolvimento-nao-usar-em-producao"
RETENCAO_DIAS = 395  # ~13 meses


def chave() -> bytes:
    valor = os.environ.get("ATRIBUICAO_CHAVE_HMAC")
    if not valor:
        warnings.warn("ATRIBUICAO_CHAVE_HMAC ausente: usando chave de desenvolvimento", stacklevel=2)
        valor = CHAVE_DEV
    return valor.encode()


def normalizar_email(email: str) -> str:
    # Só o que é seguro para qualquer provedor: espaços e caixa. Remover pontos
    # ou "+tag" vale para o Gmail mas junta pessoas diferentes em outros.
    return email.strip().lower()


def pseudonimo(email: str, chave_hmac: bytes | None = None) -> str:
    return hmac.new(chave_hmac or chave(), normalizar_email(email).encode(), hashlib.sha256).hexdigest()


CODIGO_MINUTOS = 15
CODIGO_TENTATIVAS = 5


def _hash_codigo(pid: str, codigo: str, chave_hmac: bytes | None) -> str:
    return hmac.new(chave_hmac or chave(), f"{pid}:{codigo}".encode(), hashlib.sha256).hexdigest()


def pedir_exclusao(con: sqlite3.Connection, email: str, agora: datetime | None = None,
                   chave_hmac: bytes | None = None) -> str:
    """Gera o código de confirmação e devolve para quem vai enviá-lo por e-mail.

    Gera mesmo que não exista dado ligado ao e-mail: a resposta da API é a
    mesma nos dois casos, para ninguém descobrir quais e-mails têm cadastro
    pedindo exclusão em nome dos outros. Um pedido novo substitui o anterior.
    """
    pid = pseudonimo(email, chave_hmac)
    codigo = f"{secrets.randbelow(10**6):06d}"
    expira = tempo.texto((agora or tempo.agora()) + timedelta(minutes=CODIGO_MINUTOS))
    with con:
        con.execute("INSERT OR REPLACE INTO pedidos_exclusao VALUES (?, ?, ?, 0)",
                    (pid, _hash_codigo(pid, codigo, chave_hmac), expira))
    return codigo


def confirmar_exclusao(con: sqlite3.Connection, email: str, codigo: str, agora: datetime | None = None,
                       chave_hmac: bytes | None = None) -> dict[str, int] | None:
    """Apaga os dados se o código confere. None = código inválido, vencido ou esgotado.

    Seis dígitos são um milhão de combinações; com 5 tentativas por código,
    a chance de acertar no chute é 1 em 200 mil por pedido, e pedir de novo
    é limitado por IP na API.
    """
    pid = pseudonimo(email, chave_hmac)
    pedido = con.execute("SELECT codigo_hash, expira, tentativas FROM pedidos_exclusao WHERE pessoa_id = ?",
                         (pid,)).fetchone()
    if not pedido:
        return None
    if pedido["tentativas"] >= CODIGO_TENTATIVAS or tempo.ler(pedido["expira"]) < (agora or tempo.agora()):
        with con:
            con.execute("DELETE FROM pedidos_exclusao WHERE pessoa_id = ?", (pid,))
        return None
    if not hmac.compare_digest(pedido["codigo_hash"], _hash_codigo(pid, codigo.strip(), chave_hmac)):
        with con:
            con.execute("UPDATE pedidos_exclusao SET tentativas = tentativas + 1 WHERE pessoa_id = ?", (pid,))
        return None
    with con:
        con.execute("DELETE FROM pedidos_exclusao WHERE pessoa_id = ?", (pid,))
    return excluir_titular(con, email, chave_hmac)


def excluir_titular(con: sqlite3.Connection, email: str, chave_hmac: bytes | None = None) -> dict[str, int]:
    """Apaga tudo que liga ao titular (LGPD art. 18, VI).

    Apaga: eventos com o pseudônimo dele, os vínculos aparelho-pessoa e os
    eventos anônimos dos aparelhos que só ele usou (são dele, por dedução).
    Aparelho compartilhado com outra pessoa perde só o vínculo: os eventos
    anônimos dele não são atribuíveis a este titular e podem ser de outro.
    """
    pid = pseudonimo(email, chave_hmac)
    aparelhos = [r[0] for r in con.execute("SELECT anon_id FROM vinculos WHERE pessoa_id = ?", (pid,))]
    exclusivos = [
        a for a in aparelhos
        if con.execute("SELECT COUNT(*) FROM vinculos WHERE anon_id = ? AND pessoa_id != ?", (a, pid)).fetchone()[0] == 0
    ]
    with con:
        n_pessoa = con.execute("DELETE FROM eventos WHERE pessoa_id = ?", (pid,)).rowcount
        n_anon = 0
        for a in exclusivos:
            n_anon += con.execute("DELETE FROM eventos WHERE anon_id = ? AND pessoa_id IS NULL", (a,)).rowcount
            con.execute("DELETE FROM etapas WHERE anon_id = ?", (a,))
            con.execute("DELETE FROM consentimentos WHERE anon_id = ?", (a,))
        n_vinc = con.execute("DELETE FROM vinculos WHERE pessoa_id = ?", (pid,)).rowcount
    return {"eventos_identificados": n_pessoa, "eventos_anonimos": n_anon, "vinculos": n_vinc}


def aplicar_retencao(con: sqlite3.Connection, dias: int = RETENCAO_DIAS, agora: datetime | None = None) -> int:
    """Apaga eventos e vínculos mais velhos que o prazo. Devolve eventos apagados.

    Consentimento velho só sai quando o aparelho não tem mais nenhum evento:
    ele é a prova de que a coleta foi autorizada e precisa durar enquanto
    houver dado coletado com base nele.
    """
    limite = tempo.texto((agora or tempo.agora()) - timedelta(days=dias))
    with con:
        n = con.execute("DELETE FROM eventos WHERE momento < ?", (limite,)).rowcount
        con.execute("DELETE FROM etapas WHERE momento < ?", (limite,))
        con.execute("DELETE FROM vinculos WHERE momento < ?", (limite,))
        con.execute(
            "DELETE FROM consentimentos WHERE momento < ? AND anon_id NOT IN (SELECT anon_id FROM eventos)",
            (limite,),
        )
    return n
