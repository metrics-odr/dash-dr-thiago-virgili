# cron-job.org — disparo do build a cada 30 minutos

O `workflow_dispatch` só funciona com o workflow na `main` (já está). O token do GitHub
você gera e cadastra separadamente (**fine-grained**, só este repositório, **Actions: Read and write**).
Em cada bloco abaixo, copie só o conteúdo do bloco (1 clique).

## URL
```
https://api.github.com/repos/metrics-odr/dash-dr-thiago-virgili/actions/workflows/deploy.yml/dispatches
```

## Método
```
POST
```

## Agenda
```
A cada 30 minutos
```

## Headers (cada nome e cada valor em bloco separado)

Header 1 — nome
```
Accept
```
Header 1 — valor
```
application/vnd.github+json
```

Header 2 — nome
```
Authorization
```
Header 2 — valor
```
Bearer Insira TOKEN_AQUI
```
> Troque `Insira TOKEN_AQUI` pelo seu token (mantenha a palavra `Bearer` e o espaço).

Header 3 — nome
```
X-GitHub-Api-Version
```
Header 3 — valor
```
2022-11-28
```

Header 4 — nome
```
Content-Type
```
Header 4 — valor
```
application/json
```

## Body
```
{"ref":"main"}
```

## Resposta esperada
HTTP **204** = ok. 401/403 = token errado ou sem *Actions: write*. 404 = owner/repo/arquivo errado.
422 = workflow não está na `main`.
