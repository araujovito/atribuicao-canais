from app.identidade import aparelhos_ambiguos, mapa_aparelhos, resolver


def test_celular_e_computador_viram_a_mesma_pessoa():
    # Ana clica no anúncio pelo celular, depois faz login no celular e no computador.
    mapa = mapa_aparelhos([("celular-ana", "ana"), ("pc-ana", "ana")])
    assert resolver("celular-ana", None, mapa) == "p:ana"
    assert resolver("pc-ana", None, mapa) == "p:ana"


def test_eventos_antes_do_login_herdam_a_pessoa():
    # O vínculo vale para o aparelho, não só para os eventos depois do login.
    mapa = mapa_aparelhos([("celular-ana", "ana")])
    assert resolver("celular-ana", None, mapa) == "p:ana"


def test_aparelho_sem_login_fica_anonimo():
    assert resolver("visitante", None, {}) == "a:visitante"


def test_computador_compartilhado_nao_funde_pessoas():
    mapa = mapa_aparelhos([("pc-familia", "ana"), ("pc-familia", "bruno"), ("celular-ana", "ana")])
    assert aparelhos_ambiguos(mapa) == {"pc-familia"}
    # Eventos anônimos do PC compartilhado não vão para ninguém...
    assert resolver("pc-familia", None, mapa) == "a:pc-familia"
    # ...mas eventos com login continuam de quem logou, e Ana e Bruno seguem separados.
    assert resolver("pc-familia", "bruno", mapa) == "p:bruno"
    assert resolver("celular-ana", None, mapa) == "p:ana"


def test_prefixo_evita_colisao_entre_aparelho_e_pessoa():
    assert resolver("x", None, {}) != resolver("y", "x", {})
