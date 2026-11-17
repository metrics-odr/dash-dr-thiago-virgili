# CLAUDE.md — Dashboard Dr. Thiago Virgili | Contour Clinique

> Lido automaticamente pelo Claude Code. Mantenha atualizado.

## ⚙️ REGRAS DE PUBLICAÇÃO (obrigatórias)

1. **Implementar direto na `main`, sempre** — sem abrir PR e sem mesclar. Autorização
   permanente do usuário: toda mudança pronta e validada vai por `git push origin main`
   (o push na `main` dispara o `deploy.yml`, que reconstrói e publica o Pages).
2. **Botão "Publicar".** Sempre que uma alteração estiver pronta e a sessão NÃO puder fazer
   push direto na `main` (ex.: sessão restrita a uma branch de desenvolvimento), o Claude
   deve abrir um botão/opção escrito **Publicar** (use `AskUserQuestion` com a opção
   "Publicar"). Ao clicar, o Claude **abre o PR e já faz a mesclagem na `main`** (squash) na
   mesma ação, para o usuário ver a alteração no navegador o quanto antes. Sem pedir
   confirmações extras.
3. Depois de publicar, acompanhar o Actions até ficar verde e informar a URL:
   https://metrics-odr.github.io/dash-dr-thiago-virgili/
4. Nunca commitar tokens. O token do cron-job.org é gerado/cadastrado pelo usuário.

## O que é

App de BI estático (HTML/CSS/JS + Chart.js via CDN) no **GitHub Pages**, reconstruído a cada
~30 min (GitHub Actions disparado pelo cron-job.org — ver `SETUP-CRON.md`). Mesmo layout/engine
do template `dash-mednexus`; só mudaram fontes de dados, rótulos e identidade visual
(preto + dourado, logo Contour em `build/logo_contour.b64`, títulos em Lora).

- **URL:** https://metrics-odr.github.io/dash-dr-thiago-virgili/
- **Somente leitura** da planilha. Nunca escrever de volta.

## Fontes (planilha "Dr Thiago | Planilha Central", id `1EcPFdCtd75HNN8xz4B7UU2KjSSkEYW4MkQRYgQArnRk`)

| Aba | gid | Colunas |
|-----|-----|---------|
| Meta Ads | `316997495` | Day, Ad ID, Campaign Name, Ad Set Name, Ad Name, Amount Spent, Impressions, Link Clicks, Landing Page Views, Leads, Messaging Conversations Started, Checkouts Initiated, Purchases, Purchases Conversion Value, status…, Creative Instagram Permalink |
| Conversas Iniciadas | `718101807` | Data (dd/mm/aaaa hh:mm:ss), entity_id, chat_id, contact_id, autor_id, Nome, Mensagem, Telefone, Agendado (SIM/NÃO), Status (etapa Kommo), Abrir Conversa (link Kommo) |
| Agendamentos | `439827908` | Data, Nome, Telefone, entity_id (= id do lead no Kommo) |
| Vendas | *futura* | definir `GID_SALES` em `build/build.py` (Data · Faturamento · Receita) |

Export CSV: `https://docs.google.com/spreadsheets/d/<ID>/export?format=csv&gid=<GID>`.
**A planilha precisa estar como "Qualquer pessoa com o link: Leitor"** (senão o build falha com 401).
Linhas "deslocadas" (células vazias omitidas) são lidas ancoradas na direita (`parse_conv_row`).

## Mapeamento no motor (importante)

- **Funil:** Impressão > Clique > Mensagem > Agendamento > Consulta > Venda.
- **Conversas Totais** = *Messaging Conversations Started* (aba Meta Ads) → CPL-T.
  **Novas Conversas** = aba Conversas Iniciadas (CRM, `leads[]`) → CPL-N.
  **Proporção** = Novas ÷ Totais (pode passar de 100% se o CRM registrar mais que o Meta).
  (Interpretação assumida: "totais" = Meta, "novas" = contatos novos no CRM.)
- `leads[].q` = **Agendamento** (JS: chaves `mqls`/`cpmql`/`tx` = Agendamentos/CPA/Tx‑Agend.; não renomear).
  Agendamento = id Kommo (final de "Abrir Conversa") OU telefone ∈ aba Agendamentos, OU Agendado = SIM, OU etapa Consulta.
  Agendamentos sem conversa viram lead extra (`bucket` "Agendado (sem conversa no CRM)", link montado por `KOMMO_LEAD_URL`+entity_id).
- `leads[].c` = **Consulta** (Status do CRM contém "consulta", ex. "4. Consulta Paga") → JS `reunioes`.
- **Página Captura Meta Ads e tabelas Campanha/Conjunto/Anúncio = 100% aba Meta Ads**, sem cruzar
  (`metaScope` zera `fL`/`fS`; Conversas = `ml`; só Gasto, CPM, CTR, Cliques, Conversas, CPL; gráficos só CPL).
- **Página Agendamentos** (`renderAgenda`): lista cada agendamento com link **Abrir conversa** (`leads[].lk`) para auditoria no CRM.
- Vendas/Faturamento/ROAS/CAC = "-" até a aba de Vendas existir (`GID_SALES`).
- Sem Page Views/ConvLP/Checkouts (campanhas de mensagem).
- Imposto Meta: `TAX_FACTOR = 1.13806` (herdado do template — **confirmar** com o cliente).

## Arquitetura / arquivos

```
build/build.py               # lê as abas (CSV), emite registros brutos; render() costura os arquivos abaixo
build/template.html          # esqueleto (placeholders __STYLES__ __APP_JS__ __DATA_JSON__ __LOGO_B64__ …)
build/identidade-visual.css  # TODAS as cores (escuro=padrão preto/dourado; claro=marfim). Trocar cor só aqui
build/estilos.css            # layout/componentes
build/app.js                 # lógica/render (filtros, tabelas, heatmap, funil, aba Relatório)
build/logo_contour.b64       # logo (webp base64) usado na sidebar e favicon
build/relatorios*.json       # Insights de Tráfego (vazios; schedule do briefing.yml desativado)
.github/workflows/deploy.yml # build + Pages (workflow_dispatch + schedule 30 min + push em build/**)
.github/workflows/briefing.yml # coletor dos Insights (só manual; Routine do Claude não criada)
GUIA-REPLICACAO.md           # detalhes da engine (filtro cruzado, tabelas, gráficos)
SETUP-CRON.md                # valores do cron-job.org
```

Engine (não muda): `app.js`, `estilos.css`, workflows. Mais detalhes de implementação em `GUIA-REPLICACAO.md`.

## Teste local
`python build/build.py --conversas-file c.csv --meta-file m.csv --agend-file a.csv --out dist/index.html`
(o sandbox do agente costuma não alcançar docs.google.com; o runner do Actions alcança, se a planilha for pública.)

## Pendências conhecidas
- Aba de Vendas (futura) → `GID_SALES` + colunas.
- Habilitar Pages (Source = GitHub Actions) e Workflow permissions = read/write nas Settings do repo, se ainda não estiverem.
- Compartilhar a planilha por link (leitor) para o Actions ler.
