import pytest

from app.canais import classificar


@pytest.mark.parametrize(
    ("kwargs", "esperado"),
    [
        ({"utm_source": "google", "utm_medium": "cpc"}, "Busca paga"),
        ({"utm_source": "instagram", "utm_medium": "paid"}, "Social pago"),
        ({"utm_source": "parceiro-x", "utm_medium": "cpc"}, "Mídia paga"),
        ({"utm_source": "newsletter", "utm_medium": "email"}, "E-mail"),
        ({"utm_source": "facebook", "utm_medium": "social"}, "Social orgânico"),
        ({"utm_source": "dv360", "utm_medium": "display"}, "Display"),
        ({"utm_source": "cupom-site", "utm_medium": "afiliado"}, "Afiliados"),
        ({"referrer": "https://www.google.com.br/"}, "Busca orgânica"),
        ({"referrer": "https://news.google.com/x"}, "Busca orgânica"),
        ({"referrer": "https://l.instagram.com/?u=x"}, "Social orgânico"),
        ({"referrer": "https://t.co/abc"}, "Social orgânico"),
        ({"referrer": "https://blog.qualquer.com.br/post"}, "Referência"),
        ({}, "Direto"),
        ({"gclid": "abc123"}, "Busca paga"),
    ],
)
def test_classificacao_basica(kwargs, esperado):
    assert classificar(**kwargs) == esperado


def test_utm_ganha_do_referrer():
    # Link de e-mail aberto no Gmail web: o referrer diz Google, a campanha diz E-mail.
    assert classificar(utm_medium="email", referrer="https://mail.google.com/") == "E-mail"


def test_fbclid_nao_vira_pago():
    # fbclid aparece em compartilhamento orgânico; não há parâmetro para ele de propósito.
    assert classificar(referrer="https://l.facebook.com/l.php") == "Social orgânico"


def test_dominio_inteiro_nao_casa_por_prefixo():
    assert classificar(referrer="https://t.com.br/") == "Referência"


def test_navegacao_interna_nao_e_origem():
    assert classificar(referrer="https://loja.exemplo.com.br/carrinho", host_proprio="exemplo.com.br") is None
    assert classificar(referrer="https://exemplo.com.br/", host_proprio="exemplo.com.br") is None


@pytest.mark.parametrize(
    ("fonte", "midia", "esperado"),
    [
        ("(direct)", "(none)", "Direto"),
        ("<Other>", "organic", "Busca orgânica"),
        ("baidu", "organic", "Busca orgânica"),  # buscador fora da lista: a mídia decide
        ("<Other>", "referral", "Referência"),
        ("<Other>", "<Other>", "Não identificado"),
        ("(data deleted)", "(data deleted)", "Não identificado"),
        ("google", "<Other>", "Busca orgânica"),
        ("Partners", "affiliate", "Afiliados"),
        ("google", "cpc", "Busca paga"),
    ],
)
def test_vocabulario_do_ga4(fonte, midia, esperado):
    assert classificar(utm_source=fonte, utm_medium=midia) == esperado
