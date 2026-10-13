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
| 1 | Análise de site (web analytics) | visitas, páginas, origem, celular x computador | Google Analytics 4, Adobe Analytics |
| 2 | Rastreamento por UTM | saber qual link/campanha trouxe a visita | GA4, todas as ferramentas abaixo |
| 3 | Junção de identidade entre aparelhos | mesma pessoa no celular e no computador | GA4 (User-ID, Google Signals), Mixpanel, Amplitude |
| 4 | Atribuição multicanal | quanto crédito cada canal recebe pela conversão | GA4, Triple Whale, Northbeam, Hyros |
| 5 | Análise de produto (funis, retenção) | onde as pessoas desistem no caminho | Mixpanel, Amplitude, Heap |
| 6 | Gravação de sessão e mapa de cliques | ver o que a pessoa fez na tela | Hotjar, Microsoft Clarity, FullStory |
| 7 | Coleta e distribuição de eventos (CDP) | coletar uma vez e mandar para vários destinos | Segment, mParticle |
| 8 | Automação de marketing | formulários, e-mails, origem e pontuação do lead | RD Station, HubSpot, Marketo |
| 9 | CRM | acompanhar o lead até virar cliente/venda | Salesforce, HubSpot, Pipedrive |
| 10 | Testes A/B e feature flags | testar versões de página | Optimizely, VWO, LaunchDarkly |
| 11 | Gestão de consentimento (LGPD) | banner de cookies e registro do "sim" | OneTrust, Cookiebot, Adopt |
| 12 | Inteligência de mercado (de fora) | estimar tráfego e ferramentas de outros sites | Similarweb, Semrush, Ahrefs, BuiltWith |

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
| 1, 2 Coleta de visitas e UTMs | `web/rastreio.js`, `app/main.py`, `app/canais.py` | em andamento: `app/canais.py` feito |
| 3 Junção de identidade entre aparelhos | `app/identidade.py` | feito |
| 4 Atribuição (5 modelos de regra + Markov) | `app/atribuicao.py` | a fazer |
| 11 Consentimento + privacidade (HMAC, exclusão, retenção) | `web/loja.html`, `app/privacidade.py`, `app/main.py` | a fazer |
| Painel comparando modelos | `web/index.html` | a fazer |
| Dados fictícios para demonstração | `scripts/gerar_dados.py` | a fazer |
| 5 Funis | — | possível próximo passo |
| Publicação online para teste real (celular + computador) | Render/Railway | pendente: conta do Vitor |

A ideia é mostrar que entendemos **como** esses serviços funcionam por dentro,
não reconstruí-los inteiros. Num ambiente real, a coleta poderia ir para o
RudderStack e a análise para o PostHog, e a lógica de atribuição daqui ficaria por
cima.

## Decisões e limites

- **Sem login ou formulário, não há junção confiável entre aparelhos.** O que
  promete isso usa dados de terceiros (Google/Meta) ou fingerprinting, que a LGPD e
  os navegadores combatem.
- **Markov de primeira ordem:** o estado não lembra de onde a pessoa veio
  (limitação documentada em teste). Evolução: ordem maior ou valores de Shapley.
- **SQLite** no protótipo; em produção, Postgres ou banco analítico + fila de eventos.
- **Dados de outros sites:** só informação pública (tecnologias usadas, estimativas,
  bibliotecas de anúncios). Dados de visitantes pertencem ao dono do site.

## Histórico

Mais recente primeiro.

- **2026-10-13** — Junção de identidade (`app/identidade.py`). Só por
  identificação própria (login/formulário). Aparelho ligado a uma pessoa
  herda a pessoa inclusive nos eventos de antes do login; aparelho ligado a
  duas ou mais pessoas fica ambíguo e não funde ninguém (descartado o
  union-find simples, que juntaria a família inteira do notebook de casa).

- **2026-10-13** — Repositório recriado do zero a partir deste documento.
  Classificação de canais (`app/canais.py`) com testes: UTM ganha do referrer,
  `gclid` conta como Busca paga, `fbclid` não (aparece em compartilhamento
  orgânico), referrer do próprio site é navegação interna e não gera toque.
