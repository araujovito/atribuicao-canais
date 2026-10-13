# Atribuição de canais

De onde vêm os clientes de um site e qual canal merece o crédito por cada
venda — inclusive quando a pessoa clica no anúncio pelo celular e compra no
computador — sem dado de terceiros e dentro da LGPD.

O projeto implementa por dentro o que GA4, RD Station, Mixpanel e afins
vendem prontos: coleta com consentimento, classificação de canais, junção de
identidade entre aparelhos, seis modelos de atribuição e um painel que
compara todos eles. Os dados são fictícios.

## Rodar

```bash
uv sync
uv run python scripts/gerar_dados.py      # 2.000 pessoas fictícias em atribuicao.db
uv run uvicorn app.main:app --reload
```

- Painel: <http://localhost:8000/>
- Loja de demonstração: <http://localhost:8000/loja>. Abra no celular e no
  computador, entre com o mesmo e-mail nos dois e compre em um deles.
- Testes: `uv run pytest`

Em produção, defina `ATRIBUICAO_CHAVE_HMAC`. Sem ela, o servidor usa uma chave
de desenvolvimento e avisa.

## Como funciona

```
navegador                      servidor                         análise
─────────                      ────────                         ───────
banner → consentimento ──────▶ registra versão do texto
visita de entrada (UTM,        confere consentimento de novo
  referrer, gclid) ──────────▶ classifica canal ──▶ eventos ──┐
login / compra (e-mail) ─────▶ HMAC do e-mail ───▶ vínculos ──┼▶ jornadas por pessoa
                                                              │   (janela de 30 dias)
                                                              └▶ 6 modelos ▶ painel
```

| Parte | Arquivo |
|---|---|
| Classificação de canais | `app/canais.py` |
| Junção entre aparelhos | `app/identidade.py` |
| Montagem das jornadas | `app/jornadas.py` |
| Modelos de atribuição | `app/atribuicao.py` |
| Pseudonimização, exclusão, retenção | `app/privacidade.py` |
| Esquema (minimização) | `app/banco.py` |
| API | `app/main.py` |
| Rastreador e loja | `web/rastreio.js`, `web/loja.html` |
| Painel | `web/index.html` |
| Dados fictícios | `scripts/gerar_dados.py` |

## Decisões

**Canais.** A UTM ganha do referrer, porque é a única informação que o dono
do link controla. `gclid` conta como Busca paga; `fbclid` não conta como pago,
porque o Facebook o acrescenta também em compartilhamentos orgânicos.

**Junção entre aparelhos só por identificação própria.** Login ou formulário
ligam o aparelho ao pseudônimo da pessoa, e todos os eventos daquele
aparelho, inclusive os de antes do login, passam a ser dela. Um aparelho
ligado a duas pessoas (o notebook da família) fica ambíguo e não funde
ninguém. O union-find simples foi descartado porque juntaria a família
inteira numa pessoa só.

**Modelos.** Primeiro toque, último toque não direto (convenção do GA4),
linear, decaimento temporal (meia-vida de 7 dias), posição 40/20/40 e Markov
de primeira ordem com efeito de remoção. Um teste garante que todo modelo
distribui exatamente as conversões e a receita existentes.

**Privacidade.** HMAC-SHA256 com chave em vez de hash puro, porque e-mail tem
pouca entropia e hash sem chave se reverte com listas vazadas. Do referrer
fica só o host; do navegador, só a classe do aparelho; e-mail e IP não são
gravados. A exclusão a pedido apaga também os eventos anônimos dos aparelhos
que só o titular usou. A retenção padrão é de 13 meses: a LGPD não fixa prazo,
e esse é a referência da CNIL para medição de audiência.

## O que os dados fictícios mostram

Com a semente padrão, 2.000 pessoas geram 459 compras, das quais cerca de 105
começam num aparelho e terminam em outro. A junção recupera 83 delas, só as de
quem fez login no celular. No último toque, a junção tira crédito de Direto e
devolve a Social pago e Busca orgânica: é a venda que "veio do nada" no
computador e na verdade começou num anúncio no celular.

**Atribuição não é causa.** No gerador, Display tem efeito zero na chance de
compra. Mesmo assim recebe cerca de 8% do crédito no Markov, tanto quanto no
primeiro toque, porque abre jornadas que sem ele não existiriam. Todo modelo
de atribuição, de regra ou baseado em dados, mede participação no caminho.
Efeito causal só se mede com teste de incrementalidade (grupo de controle sem
o anúncio). A primeira versão do gerador prometia o contrário, e o resultado
desmentiu.

## Limites

- Sem login ou formulário, não há junção confiável entre aparelhos. O que
  promete isso usa dados de terceiros ou fingerprinting.
- O Markov é de primeira ordem: o estado não lembra de onde a pessoa veio
  (limitação escrita como teste em `tests/test_atribuicao.py`). As evoluções
  possíveis são uma ordem maior ou valores de Shapley.
- SQLite no protótipo. Em produção, seria Postgres ou um banco analítico
  atrás de uma fila de eventos, com a coleta podendo ir para o RudderStack e
  a análise para o PostHog, e a lógica de atribuição daqui por cima.

O contexto completo (serviços do mercado, alternativas de código aberto e
histórico) está em [CONTEXTO.md](CONTEXTO.md).
