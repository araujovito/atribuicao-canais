"""Importa dados REAIS da base pública de GA4 do Google para o formato do projeto.

Fonte: `bigquery-public-data.ga4_obfuscated_sample_ecommerce`, eventos da
Google Merchandise Store (loja oficial do Google) de nov/2020 a jan/2021,
publicados pelo Google com anonimização (parte dos valores vira `<Other>`
ou `(data deleted)`; ver app/canais.py).

O que vira o quê:
- Cada sessão (`ga_session_id`) vira uma visita de entrada, com a origem da
  primeira página da sessão que tem `source`/`medium`. A base não preenche
  a origem no `session_start`, só nas páginas.
- Origem igual ao próprio site (`shop.googlemerchandisestore.com /
  referral`) é navegação interna: a visita fica, sem canal, como faz o
  rastreador.
- Sessão sem origem nenhuma (31% delas) vira "Não identificado".
- `purchase` vira conversão (receita em dólar; sem valor = 0) e o primeiro
  `add_to_cart` da sessão vira a etapa carrinho do funil.
- `user_pseudo_id` é o aparelho. A base não tem `user_id` (nenhum login), então
  não há junção entre aparelhos nem vínculos.
- Tablet conta como celular: o painel separa tela de toque de computador.

Amostra: os usuários cujo hash do id cai nos primeiros N% (padrão 10%). É
determinística (a mesma a cada execução) e não depende de comprar ou não,
então as taxas de conversão continuam as da base. Com a base inteira
(~270 mil usuários) o bootstrap do painel levaria minutos.

Requisitos: Google Cloud SDK com `bq` e login feito (`gcloud auth login`);
a consulta lê ~1,7 GB, cobrados do projeto informado (cota gratuita: 1 TB/mês).

Uso:
    python scripts/importar_ga4.py --projeto MEU-PROJETO            # 10% no esquema ga4
    python scripts/importar_ga4.py --projeto MEU-PROJETO --percentual 25
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.banco import conectar  # noqa: E402
from app.canais import classificar  # noqa: E402
from app.tempo import texto  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "dados" / "ga4.db"
HOST_PROPRIO = "googlemerchandisestore.com"

CONSULTA = """
WITH base AS (
  SELECT
    user_pseudo_id AS u,
    event_timestamp AS ts,
    event_name AS ev,
    device.category AS aparelho,
    ecommerce.purchase_revenue AS receita,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = "ga_session_id") AS sessao,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = "source") AS fonte,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = "medium") AS midia,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = "campaign") AS campanha
  FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE event_name IN ("page_view", "purchase", "add_to_cart")
    AND MOD(ABS(FARM_FINGERPRINT(user_pseudo_id)), 100) < @percentual
),
visitas AS (
  SELECT u, sessao, ANY_VALUE(aparelho) AS aparelho, MIN(ts) AS ts,
    ARRAY_AGG(IF(fonte IS NULL, NULL, STRUCT(fonte, midia, campanha)) IGNORE NULLS ORDER BY ts LIMIT 1)[SAFE_OFFSET(0)] AS o
  FROM base WHERE ev = "page_view" GROUP BY u, sessao
)
SELECT "visita" AS tipo, u, aparelho, ts, o.fonte, o.midia, o.campanha, NULL AS receita FROM visitas
UNION ALL
SELECT "conversao", u, aparelho, ts, NULL, NULL, NULL, receita FROM base WHERE ev = "purchase"
UNION ALL
SELECT "carrinho", u, ANY_VALUE(aparelho), MIN(ts), NULL, NULL, NULL, NULL FROM base
WHERE ev = "add_to_cart" GROUP BY u, sessao
"""


def baixar(projeto: str, percentual: int) -> str:
    """Roda a consulta pelo `bq` e devolve o CSV."""
    cmd = [
        "bq", "--quiet", "--headless", f"--project_id={projeto}", "query",
        "--use_legacy_sql=false", "--format=csv", "--max_rows=10000000",
        f"--parameter=percentual:INT64:{percentual}", CONSULTA,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"bq falhou:\n{r.stderr or r.stdout}")
    return r.stdout


def _momento(microssegundos: str) -> str:
    return texto(datetime.fromtimestamp(int(microssegundos) / 1_000_000, tz=timezone.utc))


def _aparelho(categoria: str) -> str:
    return "computador" if categoria == "desktop" else "celular"


def converter(linhas: csv.DictReader) -> tuple[list[tuple], list[tuple], dict[str, int]]:
    """Linhas do CSV -> (eventos, etapas, estatísticas). Sem rede: testável."""
    eventos, etapas = [], []
    stats = {"visitas": 0, "internas": 0, "sem_origem": 0, "compras": 0, "compras_sem_valor": 0, "carrinhos": 0}
    for ln in linhas:
        momento = _momento(ln["ts"])
        aparelho = _aparelho(ln["aparelho"])
        if ln["tipo"] == "visita":
            stats["visitas"] += 1
            fonte, midia = ln["fonte"] or None, ln["midia"] or None
            if fonte is None and midia is None:
                canal = "Não identificado"  # a base não registrou origem nenhuma na sessão
                stats["sem_origem"] += 1
            elif (fonte or "").lower().removeprefix("shop.") == HOST_PROPRIO:
                canal = None  # o próprio site: navegação interna
                stats["internas"] += 1
            else:
                canal = classificar(utm_source=fonte, utm_medium=midia)
            eventos.append((ln["u"], None, "visita", canal, fonte, midia, ln["campanha"] or None, None,
                            aparelho, 0.0, momento))
        elif ln["tipo"] == "conversao":
            stats["compras"] += 1
            valor = float(ln["receita"]) if ln["receita"] else 0.0
            stats["compras_sem_valor"] += not ln["receita"]
            eventos.append((ln["u"], None, "conversao", None, None, None, None, None, aparelho, valor, momento))
        elif ln["tipo"] == "carrinho":
            stats["carrinhos"] += 1
            etapas.append((ln["u"], "carrinho", momento))
    return eventos, etapas, stats


def gravar(caminho: Path, eventos: list[tuple], etapas: list[tuple]) -> None:
    if str(caminho).startswith(("postgresql://", "postgres://")):
        from app.postgres import Conexao
        con = Conexao(str(caminho), schema="ga4")
        try:
            with con:
                con.execute("DELETE FROM eventos")
                con.execute("DELETE FROM etapas")
                con.executemany("""INSERT INTO eventos (anon_id, pessoa_id, tipo, canal, utm_source, utm_medium,
                    utm_campaign, referrer_host, aparelho, valor, momento) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", eventos)
                con.executemany("INSERT INTO etapas (anon_id, etapa, momento) VALUES (?, ?, ?)", etapas)
        finally:
            con.close()
        return
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(".tmp")
    temporario.unlink(missing_ok=True)
    con = conectar(temporario)
    with con:
        con.executemany(
            """INSERT INTO eventos (anon_id, pessoa_id, tipo, canal, utm_source, utm_medium, utm_campaign,
                   referrer_host, aparelho, valor, momento) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            eventos,
        )
        con.executemany("INSERT INTO etapas (anon_id, etapa, momento) VALUES (?, ?, ?)", etapas)
    con.execute("PRAGMA journal_mode=DELETE")  # arquivo único, sem -wal ao lado
    con.close()
    # Troca atômica: o banco antigo só sai quando o novo está completo.
    temporario.replace(caminho)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--projeto", required=True, help="projeto do Google Cloud que paga a consulta")
    ap.add_argument("--percentual", type=int, default=10, help="percentual de usuários na amostra (1 a 100)")
    ap.add_argument("--destino", default=os.environ.get("DATABASE_URL", "postgresql://atribuicao:atribuicao@localhost:5432/atribuicao"))
    args = ap.parse_args()
    if not 1 <= args.percentual <= 100:
        raise SystemExit("--percentual vai de 1 a 100")
    eventos, etapas, stats = converter(csv.DictReader(io.StringIO(baixar(args.projeto, args.percentual))))
    gravar(args.destino, eventos, etapas)
    print("Dados GA4 importados: " + ", ".join(f"{k}={v}" for k, v in stats.items()))


if __name__ == "__main__":
    main()
