# Dashboard de Resultados · Dr. Thiago Virgili | Contour Clinique

Dashboard **100% na nuvem** (HTML/CSS/JS + Chart.js) que cruza o **Meta Ads** com as
**Conversas Iniciadas** (CRM Kommo) e os **Agendamentos**, publicado no **GitHub Pages** e
reconstruído a cada ~30 min (cron-job.org → GitHub Actions). Mesmo layout/engine do
template `dash-mednexus`, com a identidade visual preto + dourado da Contour.

**URL pública:** https://metrics-odr.github.io/dash-dr-thiago-virgili/

## Fontes (planilha "Dr Thiago | Planilha Central" — somente leitura)

Spreadsheet ID `1EcPFdCtd75HNN8xz4B7UU2KjSSkEYW4MkQRYgQArnRk`

| Aba | gid | Uso |
|-----|-----|-----|
| Meta Ads | `316997495` | gasto, impressões, cliques, conversas iniciadas (Meta) por anúncio/dia |
| Conversas Iniciadas | `718101807` | **Leads** = conversas de WhatsApp no CRM (sem campanha/anúncio) |
| Agendamentos | `439827908` | consultas agendadas → etapa **Agendamentos** do funil |
| Vendas | *(futura)* | preencher `GID_SALES` em `build/build.py` |

O build lê o **export CSV** (`.../export?format=csv&gid=...`). **A planilha precisa estar
compartilhada como "Qualquer pessoa com o link: Leitor"** — se estiver privada o build
falha com a mensagem `a planilha esta PRIVADA`.

## Funil e regras

`Impressões → Cliques → Conversas Iniciadas → Agendamentos → Vendas → Faturamento`

- **Agendamento** = lead cujo id do Kommo (final do link "Abrir Conversa") ou telefone
  consta em *Agendamentos*, ou com coluna *Agendado* = SIM. Agendamentos sem conversa
  correspondente entram como conversa extra (o funil nunca tem mais agendamentos que conversas).
- **Leads por anúncio:** o CRM não informa campanha/anúncio; nas tabelas por
  campanha/conjunto/anúncio (aba *Captura Meta Ads*) "Conversas" = *Messaging Conversations
  Started* do Meta Ads. Agendamentos não têm quebra por anúncio.
- Telefone mascarado (página pública). Imposto Meta (`TAX_FACTOR`) ativo por padrão.

## Arquitetura

```
cron-job.org ─POST workflow_dispatch (30 min)─▶ GitHub Actions ─▶ build/build.py ─▶ dist/index.html ─▶ GitHub Pages
```

Veja `CLAUDE.md` (contexto completo + regras de publicação) e `SETUP-CRON.md` (valores do cron-job.org).

## Rodar local

```bash
python build/build.py --conversas-file conv.csv --meta-file meta.csv --agend-file agend.csv --out dist/index.html
```
