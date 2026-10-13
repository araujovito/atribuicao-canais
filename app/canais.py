"""Classificação de cada visita em um canal de marketing.

A regra segue a lógica do agrupamento padrão do GA4, simplificada e em
português: UTM explícita ganha de tudo; sem UTM, olha-se o referrer; sem
referrer, é Direto.

Decisões:
- UTM ganha do referrer porque é a única informação que o *dono* do link
  controla. Um link de e-mail aberto no Gmail web chega com referrer
  mail.google.com, mas a campanha é E-mail.
- `gclid` sem UTM conta como Busca paga: é o auto-tagging do Google Ads, e
  muita conta só usa ele.
- `fbclid` NÃO conta como pago: o Facebook acrescenta esse parâmetro também em
  links compartilhados organicamente. Tratar como pago infla o canal pago.
- Referrer do próprio site não é uma nova origem (é navegação interna); devolve
  None para quem chama ignorar o toque.
"""

from __future__ import annotations

from urllib.parse import urlparse

BUSCADORES = ("google.", "bing.", "yahoo.", "duckduckgo.", "ecosia.", "yandex.", "baidu.")
SOCIAIS = (
    "facebook.", "instagram.", "linkedin.", "twitter.", "x.com", "t.co",
    "tiktok.", "youtube.", "pinterest.", "reddit.", "whatsapp.", "wa.me",
    "lnkd.in", "fb.me", "l.facebook.", "lm.facebook.",
)
MIDIAS_PAGAS = {"cpc", "ppc", "paid", "pago", "paidsearch", "paid_search", "cpm", "cpv"}
MIDIAS_SOCIAIS = {"social", "social-network", "social-media", "sm", "social_organico"}
MIDIAS_EMAIL = {"email", "e-mail", "e_mail", "newsletter"}
MIDIAS_DISPLAY = {"display", "banner", "programatica", "programmatic"}
MIDIAS_AFILIADOS = {"affiliate", "afiliado", "afiliados"}

CANAIS = (
    "Busca paga",
    "Social pago",
    "Mídia paga",
    "Display",
    "E-mail",
    "Afiliados",
    "Social orgânico",
    "Busca orgânica",
    "Referência",
    "Direto",
)


def _host(url: str | None) -> str:
    if not url:
        return ""
    host = urlparse(url if "//" in url else f"//{url}").hostname or ""
    return host.lower().removeprefix("www.")


def _casa(host_ou_fonte: str, lista: tuple[str, ...]) -> bool:
    alvo = host_ou_fonte.lower().removeprefix("www.")
    if alvo and "." not in alvo:
        alvo += "."  # utm_source=facebook vira "facebook." e casa com a lista
    for item in lista:
        if item.endswith("."):
            # Prefixo de nome: "google." pega google.com, google.com.br e news.google.com.
            if alvo.startswith(item) or f".{item}" in f".{alvo}":
                return True
        elif alvo == item or alvo.endswith(f".{item}"):
            # Domínio inteiro: "t.co" não pode casar com "t.com.br".
            return True
    return False


def classificar(
    utm_source: str | None = None,
    utm_medium: str | None = None,
    referrer: str | None = None,
    host_proprio: str | None = None,
    gclid: str | None = None,
) -> str | None:
    """Devolve o nome do canal, ou None se a visita é navegação interna."""
    fonte = (utm_source or "").strip().lower()
    midia = (utm_medium or "").strip().lower()

    if midia or fonte:
        if midia in MIDIAS_PAGAS:
            if _casa(fonte, SOCIAIS):
                return "Social pago"
            if _casa(fonte, BUSCADORES):
                return "Busca paga"
            return "Mídia paga"
        if midia in MIDIAS_EMAIL or fonte in MIDIAS_EMAIL:
            return "E-mail"
        if midia in MIDIAS_DISPLAY:
            return "Display"
        if midia in MIDIAS_AFILIADOS:
            return "Afiliados"
        if midia in MIDIAS_SOCIAIS or _casa(fonte, SOCIAIS):
            return "Social orgânico"
        if midia == "organic" and _casa(fonte, BUSCADORES):
            return "Busca orgânica"
        if midia == "referral":
            return "Referência"
        # UTM preenchida mas fora do vocabulário: melhor um balde explícito do
        # que adivinhar. Aparece no painel e força a corrigir a campanha.
        return "Mídia paga" if "pag" in midia or "paid" in midia else "Referência"

    if gclid:
        return "Busca paga"

    host = _host(referrer)
    if not host:
        return "Direto"
    if host_proprio and (host == host_proprio or host.endswith(f".{host_proprio}")):
        return None
    if _casa(host, BUSCADORES):
        return "Busca orgânica"
    if _casa(host, SOCIAIS):
        return "Social orgânico"
    return "Referência"
