"""Gera dados fictícios para o painel: pessoas, aparelhos, toques e compras.

Nenhum dado real: e-mails em `exemplo.invalid` (domínio reservado, RFC 2606),
identificadores aleatórios, semente fixa para o resultado ser reproduzível.

O comportamento dos canais é escrito de propósito para os modelos
discordarem, como acontece no mundo real:
- Social pago e Display abrem jornadas (topo de funil) e quase nunca fecham;
- Busca paga, E-mail e Direto aparecem perto da compra;
- Social pago conta como mais um toque; Display não muda nada na chance de
  compra;
- E-mail aumenta a chance de comprar.

Achado que o Display deixa à mostra: mesmo com efeito zero na compra, ele
recebe ~8% do crédito no Markov (com a semente padrão), tanto quanto no
primeiro toque. O efeito de remoção pergunta "o que acontece com as
jornadas que passam por aqui se o canal some", e no dado as jornadas que
começam por Display morrem sem ele. Nenhum modelo de atribuição, de regra ou
de dados, mede causa; para isso existe teste de incrementalidade (grupo
de controle sem o anúncio).
- Parte das pessoas começa no celular e compra no computador. Só uma parte
  delas faz login no celular; as outras ficam sem junção possível, que é o
  limite honesto do método.
- Alguns computadores são compartilhados por duas pessoas (casa de família).

Uso:
    python scripts/gerar_dados.py                 # 2.000 pessoas em atribuicao.db
    python scripts/gerar_dados.py --pessoas 500 --banco outro.db
    python scripts/gerar_dados.py --substituir    # apaga o que houver e gera de novo
"""

from __future__ import annotations

import argparse
import random
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.banco import conectar  # noqa: E402
from app.privacidade import pseudonimo  # noqa: E402
from app.tempo import agora, texto  # noqa: E402

PRIMEIRO_TOQUE = {
    "Social pago": 0.24, "Busca orgânica": 0.20, "Busca paga": 0.14, "Display": 0.16,
    "Social orgânico": 0.10, "Afiliados": 0.06, "Referência": 0.05, "E-mail": 0.05,
}
TOQUES_SEGUINTES = {
    "Busca paga": 0.24, "Direto": 0.24, "E-mail": 0.18, "Busca orgânica": 0.14,
    "Social orgânico": 0.08, "Display": 0.06, "Social pago": 0.06,
}
UTM = {
    "Busca paga": ("google", "cpc"), "Social pago": ("instagram", "paid"), "Display": ("dv360", "display"),
    "E-mail": ("newsletter", "email"), "Afiliados": ("blog-do-cafe", "afiliado"),
    "Social orgânico": ("facebook", "social"),
}
REFERRER = {"Busca orgânica": "google.com.br", "Referência": "guiadocafe.com.br"}


def sortear(pesos: dict[str, float], rng: random.Random) -> str:
    return rng.choices(list(pesos), weights=list(pesos.values()))[0]


def chance_de_compra(canais: list[str]) -> float:
    # Display não entra nem na contagem de toques: se entrasse, cada impressão
    # aumentaria a chance de compra só por alongar a jornada.
    uteis = [c for c in canais if c != "Display"]
    p = 0.04 + 0.07 * min(len(uteis), 5)
    p += 0.12 if "E-mail" in canais else 0
    p += 0.08 if "Busca paga" in canais else 0
    p += 0.05 if "Busca orgânica" in canais else 0
    return min(p, 0.75)


class BancoComDados(Exception):
    pass


def gerar(caminho: Path, n_pessoas: int, semente: int, hoje: datetime, substituir: bool = False) -> dict[str, int]:
    rng = random.Random(semente)
    con = conectar(caminho)
    # O gerador começa apagando tudo. Num banco que já recebeu coleta da loja
    # (ou de um site de verdade), isso perderia dado sem volta.
    existentes = con.execute("SELECT COUNT(*) FROM eventos").fetchone()[0]
    if existentes and not substituir:
        con.close()
        raise BancoComDados(f"{caminho} já tem {existentes} eventos; use --substituir para apagar e gerar de novo")
    with con:
        for tabela in ("eventos", "vinculos", "consentimentos"):
            con.execute(f"DELETE FROM {tabela}")

    eventos, vinculos, consent = [], [], []
    pcs_compartilhados: list[str] = []
    stats = {"pessoas": n_pessoas, "compras": 0, "compras_entre_aparelhos": 0}

    for i in range(n_pessoas):
        pid = pseudonimo(f"pessoa{i}@exemplo.invalid")
        perfil = rng.choices(["so_celular", "dois", "so_computador"], weights=[0.55, 0.30, 0.15])[0]
        celular = str(uuid.UUID(int=rng.getrandbits(128))) if perfil != "so_computador" else None
        computador = None
        if perfil != "so_celular":
            if pcs_compartilhados and rng.random() < 0.25:
                computador = pcs_compartilhados.pop()
            else:
                computador = str(uuid.UUID(int=rng.getrandbits(128)))
                if rng.random() < 0.10:
                    pcs_compartilhados.append(computador)

        inicio = hoje - timedelta(days=rng.uniform(1, 85), hours=rng.uniform(0, 23))
        canais = [sortear(PRIMEIRO_TOQUE, rng)]
        while rng.random() < 0.55 and len(canais) < 7:
            canais.append(sortear(TOQUES_SEGUINTES, rng))

        t = inicio
        aparelhos_usados = set()
        for k, canal in enumerate(canais):
            # Quem tem os dois aparelhos começa no celular e migra para o computador.
            if perfil == "dois":
                anon = celular if k < max(1, len(canais) // 2) else computador
            else:
                anon = celular or computador
            if t > hoje:
                break
            aparelhos_usados.add(anon)
            fonte, midia = UTM.get(canal, (None, None))
            ref = REFERRER.get(canal)
            eventos.append((anon, None, "visita", canal, fonte, midia, None, ref,
                            "celular" if anon == celular else "computador", 0.0, texto(t)))
            t += timedelta(days=rng.expovariate(1 / 2.5), hours=rng.uniform(0, 5))

        ultimo_aparelho = computador if perfil == "dois" else (celular or computador)
        if rng.random() < chance_de_compra(canais) and t <= hoje:
            valor = round(min(rng.lognormvariate(4.3, 0.6), 900), 2)
            eventos.append((ultimo_aparelho, pid, "conversao", None, None, None, None, None,
                            "celular" if ultimo_aparelho == celular else "computador", valor,
                            texto(t)))
            vinculos.append((ultimo_aparelho, pid, texto(t)))
            stats["compras"] += 1
            if perfil == "dois" and len(aparelhos_usados) > 1:
                stats["compras_entre_aparelhos"] += 1
        # Login no celular: sem ele, não há como saber que é a mesma pessoa.
        if perfil == "dois" and rng.random() < 0.6:
            vinculos.append((celular, pid, texto(inicio)))
        # Login no computador (área do cliente, lista de desejos) sem comprar.
        if computador and rng.random() < 0.3:
            vinculos.append((computador, pid, texto(inicio)))

        for anon in aparelhos_usados | {ultimo_aparelho}:
            consent.append((anon, "v1", 1, texto(inicio)))

    with con:
        con.executemany(
            """INSERT INTO eventos (anon_id, pessoa_id, tipo, canal, utm_source, utm_medium, utm_campaign,
                   referrer_host, aparelho, valor, momento) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            eventos,
        )
        con.executemany("INSERT OR IGNORE INTO vinculos VALUES (?, ?, ?)", vinculos)
        con.executemany(
            "INSERT INTO consentimentos (anon_id, versao, aceito, momento) VALUES (?, ?, ?, ?)", consent
        )
    stats["eventos"] = len(eventos)
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pessoas", type=int, default=2000)
    ap.add_argument("--semente", type=int, default=42)
    ap.add_argument("--banco", type=Path, default=Path(__file__).resolve().parent.parent / "atribuicao.db")
    ap.add_argument("--substituir", action="store_true", help="apaga os dados que já existirem no banco")
    args = ap.parse_args()
    try:
        stats = gerar(args.banco, args.pessoas, args.semente, agora(), args.substituir)
    except BancoComDados as e:
        raise SystemExit(f"Nada foi alterado: {e}") from None
    print(f"{args.banco}: " + ", ".join(f"{k}={v}" for k, v in stats.items()))


if __name__ == "__main__":
    main()
