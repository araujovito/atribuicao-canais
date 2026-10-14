# Contexto do projeto

Documento de referência: o que o projeto quer resolver, quais serviços o mercado
vende para isso e quais repositórios de código aberto usamos (ou podemos usar)
para cada um.

## Objetivo

Saber **de onde vêm os clientes** de um site e **qual canal merece o crédito** por
cada conversão — inclusive quando a pessoa começa no celular e termina no
computador — respeitando a LGPD.

Uso: projeto de portfólio pessoal. Não usa dados reais de ninguém.

## Serviços do mercado

| # | Serviço | O que resolve | Quem vende (exemplos) |
|---|---|---|---|
| 1 | Análise de site (web analytics) | visitas, páginas, origem, celular x computador | feito (código por e-mail) |
| 2 | Rastreamento por UTM | saber qual link/campanha trouxe a visita | feito (token + piso de 30 dias) |
| 3 | Junção de identidade entre aparelhos | mesma pessoa no celular e no computador | feito (`app/acesso.py`) |
| 4 | Atribuição multicanal | quanto crédito cada canal recebe pela conversão | feito (`app/limite.py`) |
| 5 | Análise de produto (funis, retenção) | onde as pessoas desistem no caminho | feito (`app/funis.py`) |
| 6 | Gravação de sessão e mapa de cliques | ver o que a pessoa fez na tela | configuração pronta (`render.yaml`); falta a conta do Vitor |
| 7 | Coleta e distribuição de eventos (CDP) | coletar uma vez e mandar para vários destinos | CI feito; repositório no GitHub aguarda decisão (público ou privado) |
| 8 | Automação de marketing | formulários, e-mails, origem e pontuação do lead | feito (`app/incrementalidade.py`) |
| 9 | CRM | acompanhar o lead até virar cliente/venda | feito (Markov de 2ª ordem) |
| 10 | Testes A/B e feature flags | testar versões de página | feito (`app/incerteza.py`) |
| 11 | Gestão de consentimento (LGPD) | banner de cookies e registro do "sim" | feito (`app/verdade.py`) |
| 12 | Inteligência de mercado (de fora) | estimar tráfego e ferramentas de outros sites | feito |

## Repositórios de código aberto por serviço

| Serviço | Repositório | Observação |
|---|---|---|
| 1, 2 Análise de site | [matomo-org/matomo](https://github.com/matomo-org/matomo) | o "GA4 aberto"; tem User-ID; leve |
| 1, 2 Análise de site | [plausible/analytics](https://github.com/plausible/analytics) | simples, sem cookies |
| 1, 2 Análise de site | [umami-software/umami](https://github.com/umami-software/umami) | simples, fácil de instalar |
| 3, 5, 6, 10 Produto + identidade + gravação + A/B | [PostHog/posthog](https://github.com/PostHog/posthog) | o mais completo; pesado (ClickHouse) |
| 6 Gravação de sessão | [openreplay/openreplay](https://github.com/openreplay/openreplay) | alternativa ao Hotjar |
| 7 Coleta de eventos | [rudderlabs/rudder-server](https://github.com/rudderlabs/rudder-server) | alternativa ao Segment |
| 7 Coleta de eventos | [snowplow/snowplow](https://github.com/snowplow/snowplow) | padrão de mercado; mais técnico |
| 8 Automação de marketing | [mautic/mautic](https://github.com/mautic/mautic) | o mais próximo do RD Station |
| 9 CRM | [twentyhq/twenty](https://github.com/twentyhq/twenty) | CRM moderno |
| 10 Testes A/B | [growthbook/growthbook](https://github.com/growthbook/growthbook) | A/B e feature flags |
| 11 Consentimento | [orestbida/cookieconsent](https://github.com/orestbida/cookieconsent) | banner de consentimento leve |

Atenção às licenças antes de qualquer uso comercial: PostHog, Matomo e RudderStack
têm partes com licenças que restringem oferecer o produto como serviço a terceiros.

## O que este repositório implementa (próprio, sem depender dos acima)

| Serviço | Onde | Status |
|---|---|---|
| 1, 2 Coleta de visitas e UTMs | `web/rastreio.js`, `app/main.py`, `app/canais.py` | feito |
| 3 Junção de identidade entre aparelhos | `app/identidade.py` | feito |
| 4 Atribuição (5 modelos de regra + Markov) | `app/atribuicao.py` | feito |
| 11 Consentimento + privacidade (HMAC, exclusão, retenção) | `web/loja.html`, `app/privacidade.py`, `app/banco.py`, `app/main.py` | feito |
| Montagem das jornadas (janela de 30 dias) | `app/jornadas.py` | feito |
| Painel comparando modelos | `web/index.html` | feito |
| Dados fictícios para demonstração | `scripts/gerar_dados.py` | feito |
| 5 Funis | `app/funis.py`, `/api/etapa` | feito |
| Publicação online para teste real (celular + computador) | `render.yaml` | configurado; pendente: conta do Vitor |

A ideia é mostrar que entendemos **como** esses serviços funcionam por dentro,
não reconstruí-los inteiros. Num ambiente real, a coleta poderia ir para o
RudderStack e a análise para o PostHog, e a lógica de atribuição daqui ficaria por
cima.

## Lista de melhorias (2026-10-13)

Levantada depois da primeira versão. Cada item sai num commit próprio (ou
em par, quando dois mexem no mesmo código), e o status é atualizado junto.

| # | Item | Status |
|---|---|---|
| 1 | Exclusão a pedido sem confirmar identidade: qualquer um apaga dados de qualquer e-mail | a fazer |
| 2 | `POST /api/retencao?dias=0` aberto apaga o banco inteiro | a fazer |
| 3 | Painel e API de análise sem autenticação | a fazer |
| 4 | Sem limite de requisições: dá para encher o banco de eventos falsos | a fazer |
| 5 | Funis (visita → login → carrinho → compra) por canal | a fazer |
| 6 | Publicação online (Render/Railway) | a fazer |
| 7 | Repositório no GitHub + testes no CI | a fazer |
| 8 | Teste de incrementalidade (grupo de controle) contra os modelos | a fazer |
| 9 | Markov de 1ª ordem não lembra a origem | a fazer |
| 10 | Créditos sem margem de erro | a fazer |
| 11 | Modelos não comparados com a verdade conhecida do gerador | a fazer |
| 12 | Uma conexão SQLite compartilhada entre requisições | a fazer |
| 13 | Painel recalcula tudo a cada acesso | feito (cache por versão dos dados) |
| 14 | Datas sem fuso horário | feito (`app/tempo.py`) |
| 15 | Rastreador só funciona no mesmo domínio (sem CORS) | feito (`ATRIBUICAO_ORIGENS`) |
| 16 | `gerar_dados.py` apaga o banco sem perguntar | feito (`--substituir`) |
| 17 | README sem imagem do painel e sem licença | feito (imagens em `docs/`, licença MIT) |
| 18 | Consentimento único, sem finalidades separadas nem política de privacidade | feito (medição e junção à parte + `/privacidade`) |

## Decisões e limites

- **Sem login ou formulário, não há junção confiável entre aparelhos.** O que
  promete isso usa dados de terceiros (Google/Meta) ou fingerprinting, que a LGPD e
  os navegadores combatem.
- **Markov de 1ª e 2ª ordem.** A 1ª não lembra de onde a pessoa veio
  (limitação escrita em teste); a 2ª lembra, ao custo de estimar ~74 estados
  em vez de 9 com o mesmo volume de jornadas. Os dois ficam no painel.
  Shapley foi descartado: com a função de valor usual (conversões das
  jornadas cujo conjunto de canais cabe na coalizão), ele se reduz a dividir
  cada conversão igualmente entre os canais distintos da jornada.
- **Atribuição não é causa.** No dado fictício, Display tem efeito zero na
  compra e mesmo assim recebe 4,5% das compras no Markov, perto dos 5,3% do
  primeiro toque, porque abre jornadas (era ~8% antes do teste de
  incrementalidade, que tira o Display de metade das pessoas expostas). Todo modelo de atribuição mede
  participação no caminho; efeito causal só com teste de incrementalidade
  (grupo de controle sem o anúncio), que agora está no painel.
- **Incrementalidade tem pouco poder com amostra pequena.** Com 2.000
  pessoas, nenhum dos dois testes distingue o efeito de zero (efeito mínimo
  detectável de 11 a 12 compras por 100 pessoas). Com 20.000, Social pago dá
  +5,6 (IC 3,4 a 7,8; o real é +7, diluído) e Display, −0,8 (IC −3,3 a 1,7;
  o real é 0).
- **Mais perto da verdade, aqui, é o último toque.** Com a verdade do
  gerador (Shapley sobre a chance de compra), 8% do crédito do último toque
  está no canal errado, contra ~17% no Markov e 22% no primeiro toque. É
  propriedade da regra do gerador (E-mail e Busca paga, que mais causam
  compra, aparecem perto do fim), não prova de que o último toque seja melhor
  em geral. O ponto é ter uma régua: em dado real, ela vem do teste de
  incrementalidade.
- **SQLite** no protótipo; em produção, Postgres ou banco analítico + fila de eventos.
- **Dados de outros sites:** só informação pública (tecnologias usadas, estimativas,
  bibliotecas de anúncios). Dados de visitantes pertencem ao dono do site.

## Histórico

Mais recente primeiro.

- **2026-10-13** — Dados reais (3/4): painel escolhe entre dados fictícios e
  Google Merchandise Store. O banco do GA4 abre só para leitura (a retenção de
  13 meses apagaria dados de 2020), valores em dólar, junção declarada como
  inexistente e etapa de login escondida. Primeira carga ~17 s, depois cache.

- **2026-10-13** — Dados reais (2/4): `scripts/importar_ga4.py` traz a
  base pública de GA4 do Google (Google Merchandise Store, nov/2020 a
  jan/2021) para `dados/ga4.db`, fora do git. Amostra determinística de
  10% dos usuários: 27 mil usuários, 33,5 mil sessões, 554 compras. 31% das
  sessões não têm origem na base ("Não identificado"); 10% são internas.

- **2026-10-13** — Dados reais (1/4): classificador entende o vocabulário
  do GA4 (`(direct) / (none)`, valores anonimizados `<Other>` e
  `(data deleted)`) e trata mídia `organic` como Busca orgânica mesmo sem
  buscador conhecido. Canal novo: "Não identificado".

- **2026-10-13** — Item 17: README reescrito (variáveis de ambiente,
  arquitetura nova, tabela incrementalidade × crédito, comparação com a
  verdade), imagens do painel e do banner em `docs/`, licença MIT. Números
  da semente padrão atualizados (431 compras; Display 4,5% no Markov).

- **2026-10-13** — Item 6 (parte local): `render.yaml` (plano gratuito,
  segredos sorteados pelo Render, proxy ligado), rota `/saude` e
  `ATRIBUICAO_GERAR_DEMO` para recriar os dados fictícios ao subir com o
  banco vazio. Build e start simulados num export limpo.

- **2026-10-13** — Item 7 (parte local): GitHub Actions roda `uv sync
  --locked` + pytest + checagem de sintaxe do rastreador. Simulado num
  clone limpo: 89 testes passam. Falta criar o repositório.

- **2026-10-13** — Item 11: verdade do gerador (Shapley exato sobre a
  regra de compra de cada pessoa) gravada em tabela própria; painel ganhou
  a coluna Verdade e a linha "crédito no canal errado". Último toque 8%,
  Markov ~17%, primeiro toque 22%.

- **2026-10-13** — Item 8: teste de incrementalidade (ghost ads) para
  Display e Social pago, 50% controle. Validação contra o efeito verdadeiro
  do gerador em 10 sementes achou dois vieses para zero: janela de conversão
  aberta (corrigido: só entra quem foi sorteado há mais de 30 dias) e
  diluição por aparelho sem login (~20–25%, documentado). Contaminação por
  computador compartilhado documentada em teste. Os números da semente
  padrão mudaram (431 compras, 84 entre aparelhos) porque o controle perde
  os toques do canal.

- **2026-10-13** — Item 5: funil aberto visita → login → carrinho → compra
  por canal de entrada (primeiro toque da pessoa juntada). Etapas em tabela
  própria; exclusão e retenção cobrem a tabela. Loja ganhou carrinho. Nos
  dados fictícios, Display tem a pior compra/visita (11,4%, contra 19,5% no
  total), coerente com o efeito zero que o gerador dá a ele.

- **2026-10-13** — Item 10: intervalo de 95% por bootstrap de pessoas
  (100 réplicas, ~3 s, coberto pelo cache). Leitura dos dados fictícios:
  último toque tem margens de ±4–5 p.p. nos canais grandes; Markov, ±1,5–2.
  Os modelos de um toque só jogam fora informação e balançam mais.

- **2026-10-13** — Item 9: Markov de ordem k; o painel mostra 1ª e 2ª.
  Sistema resolvido por Gauss-Seidel (matriz esparsa) em vez de eliminação de
  Gauss: 18 ms para a 2ª ordem com os dados fictícios. Shapley descartado
  (ver Decisões e limites).

- **2026-10-13** — Item 18: consentimento por finalidade (medição; junção
  entre aparelhos), caixas desmarcadas, "Aceitar tudo", "Salvar escolhas" e
  "Recusar tudo". Sem junção, o e-mail nem sai do navegador e o servidor não
  liga. Retirar a junção desfaz os vínculos do aparelho. Página
  `/privacidade` descreve o que o código faz. Migração do banco antigo.

- **2026-10-13** — Item 16: `gerar_dados.py` recusa banco que já tem
  eventos e não altera nada; apagar exige `--substituir`.

- **2026-10-13** — Item 15: CORS só para as origens de
  `ATRIBUICAO_ORIGENS`; "*" é ignorado. Sem o cabeçalho Authorization
  liberado, as rotas de admin continuam só no mesmo domínio. O rastreador
  aponta para o serviço com `data-api`.

- **2026-10-13** — Item 13: cache do painel por (janela, versão dos dados).
  Versão = contador mantido por triggers. Descartada a assinatura por
  contagem/ids: sem AUTOINCREMENT o SQLite reaproveita o id da última linha
  apagada. Cálculo medido em 63 ms com 4,8 mil eventos; o ganho cresce com o
  volume e com o bootstrap (item 10).

- **2026-10-13** — Item 4: limite por IP em memória (60 eventos/min,
  5 pedidos de exclusão/hora, 10 confirmações/hora, 20 consentimentos e
  identificações/min). IP só em memória. Atrás de proxy, vale o último
  endereço do X-Forwarded-For. anon_id restrito a letras, dígitos e hífen.

- **2026-10-13** — Item 1: exclusão em dois passos. Código de 6 dígitos
  enviado ao e-mail (simulado no log, `app/correio.py`), gravado só como
  HMAC, vence em 15 min, queima após 5 erros, uso único. Resposta igual
  exista ou não o e-mail. Rota de atendimento com token para pedidos por
  outros canais. Fluxo conferido na loja em Chromium headless.

- **2026-10-13** — Itens 2 e 3: painel e retenção exigem token de
  administrador (`ATRIBUICAO_TOKEN_ADMIN`; sem ele, sorteado na subida e
  escrito no log). Retenção com piso de 30 dias: `dias=0` agora dá 422.
  Painel pede o token e guarda só na aba. Conferido em Chromium headless.

- **2026-10-13** — Item 12: uma conexão SQLite por requisição (dependência
  do FastAPI), WAL e espera de até 5 s por escrita concorrente. Teste com
  40 eventos simultâneos em 8 threads.

- **2026-10-13** — Item 14: datas sempre em UTC com deslocamento
  (`app/tempo.py`). Texto ISO no mesmo formato mantém a ordem alfabética
  igual à cronológica, então o SQL compara datas como texto sem erro.

- **2026-10-13** — Lista de 18 melhorias registrada (seção própria), com
  as falhas de segurança primeiro.

- **2026-10-13** — README para quem chega sem contexto: como rodar,
  arquitetura, decisões, o que os dados fictícios mostram e limites.

- **2026-10-13** — Painel (`web/index.html`), sem biblioteca de gráficos:
  indicadores, barras pareadas com e sem junção entre aparelhos, matriz canal
  × modelo e visitas por aparelho. Paleta de duas séries validada para
  daltonismo nos dois temas. Conferido em Chromium headless (claro, escuro e
  390 px de largura, sem rolagem horizontal); hover testado na barra e na
  célula, depois de corrigir barras que roubavam o ponteiro da área de hover.

- **2026-10-13** — Dados fictícios (`scripts/gerar_dados.py`): 2.000
  pessoas, semente fixa, e-mails em `exemplo.invalid`. Com a semente padrão:
  ~460 compras, ~105 delas entre aparelhos, das quais a junção recupera ~83
  (só quem fez login no celular). Display com efeito zero recebe ~8% no
  Markov: achado registrado em "Decisões e limites".

- **2026-10-13** — Rastreador (`web/rastreio.js`) e loja de demonstração
  (`web/loja.html`) com banner de consentimento, login, compra, revogação e
  exclusão. Só a visita de entrada de cada sessão sai do navegador.
  Conferido em Chromium headless: anúncio no celular + compra no computador
  com o mesmo e-mail = 1 conversão entre aparelhos, creditada a Busca paga
  (Direto sem a junção); recusa no banner não envia nada.

- **2026-10-13** — API (`app/main.py`, FastAPI) e montagem das jornadas
  (`app/jornadas.py`). O servidor confere o consentimento de novo e recusa
  evento sem ele. `/api/painel` devolve a atribuição com e sem junção de
  aparelhos: no teste, a venda feita no computador depois do anúncio no
  celular vai para Busca paga com junção e para Direto sem ela.

- **2026-10-13** — Privacidade (`app/privacidade.py`) e esquema SQLite
  (`app/banco.py`). HMAC-SHA256 com chave secreta em vez de hash puro
  (e-mail tem pouca entropia). Exclusão do titular apaga também os eventos
  anônimos de aparelho exclusivo dele, mas não os de aparelho compartilhado.
  Retenção padrão de 13 meses (referência da CNIL; a LGPD não fixa prazo).
  Esquema minimiza na origem: sem e-mail, sem IP, referrer só o host,
  User-Agent só a classe do aparelho.

- **2026-10-13** — Atribuição (`app/atribuicao.py`): primeiro toque, último
  toque não direto, linear, decaimento temporal (meia-vida 7 dias) e posição
  40/20/40; Markov de primeira ordem com efeito de remoção, resolvido por
  eliminação de Gauss sem numpy. Teste garante que todo modelo distribui
  exatamente as conversões e a receita existentes. A limitação da primeira
  ordem (não lembra a origem) está escrita como teste.

- **2026-10-13** — Junção de identidade (`app/identidade.py`). Só por
  identificação própria (login/formulário). Aparelho ligado a uma pessoa
  herda a pessoa inclusive nos eventos de antes do login; aparelho ligado a
  duas ou mais pessoas fica ambíguo e não funde ninguém (descartado o
  union-find simples, que juntaria a família inteira do notebook de casa).

- **2026-10-13** — Repositório recriado do zero a partir deste documento.
  Classificação de canais (`app/canais.py`) com testes: UTM ganha do referrer,
  `gclid` conta como Busca paga, `fbclid` não (aparece em compartilhamento
  orgânico), referrer do próprio site é navegação interna e não gera toque.
