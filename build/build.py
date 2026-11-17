#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gera a dashboard estatica (index.html) do Dr. Thiago Virgili | Contour Clinique
a partir da planilha "Dr Thiago | Planilha Central" (3 abas + 1 futura):

  - "Meta Ads" (gid 316997495): gasto/impressoes/cliques/conversas iniciadas por anuncio/dia.
  - "Conversas Iniciadas" (gid 718101807): conversas de WhatsApp registradas no CRM
    (Kommo). FONTE dos "Leads" (Conversas Iniciadas). Nao traz campanha/anuncio.
  - "Agendamentos" (gid 439827908): consultas agendadas (Data, Nome, Telefone,
    entity_id = id do lead no Kommo). Define a etapa "Agendamentos" do funil
    (no motor do template = a coluna "MQL").
  - "Vendas" (FUTURA): quando existir, preencher GID_SALES — o codigo ja le a aba.

Cruzamentos:
  * Agendamento x Conversa: por id do lead Kommo (final do link "Abrir Conversa"),
    por telefone canonico e pela coluna "Agendado" (SIM) da propria aba Conversas.
    Agendamentos sem conversa correspondente entram como lead extra (q=1) para o
    funil nunca ter mais agendamentos que conversas.
  * Leads por anuncio: a aba Conversas NAO tem campanha/anuncio. Na pagina de
    midia paga, "Leads" por campanha/conjunto/anuncio = "Messaging Conversations
    Started" do proprio Meta Ads (campo ml em meta[]). A Visao Geral usa as
    Conversas do CRM (fonte de verdade).

Este script apenas LE as planilhas (export CSV) e emite REGISTROS BRUTOS
(leads[], meta[], sales[]) dentro do HTML; todo filtro/agregacao/grafico e'
calculado no navegador. Nunca escreve nada de volta.

Teste local: --conversas-file / --meta-file / --agend-file / --sales-file.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

SPREADSHEET_ID = "1EcPFdCtd75HNN8xz4B7UU2KjSSkEYW4MkQRYgQArnRk"
GID_META = "316997495"        # Meta Ads
GID_CONVERSAS = "718101807"   # Conversas Iniciadas (CRM Kommo) = Leads
GID_AGEND = "439827908"       # Agendamentos
GID_SALES = None              # FUTURA aba de Vendas — preencher o gid quando existir
EXPORT_URL = "https://docs.google.com/spreadsheets/d/{sid}/export?format=csv&gid={gid}"

CLIENT_NAME = "Dr. Thiago Virgili"
CLINIC_NAME = "Contour Clinique"

BRT = timezone(timedelta(hours=-3))   # horario de Brasilia (exibicao)
TAX_FACTOR = 1.13806                  # imposto/taxa da conta de mídia (13,806%) — ajuste se a conta do cliente for outra

# --------------------------------------------------------------------------- #
# Regras da aba Relatório (Top/Piores anúncios)
# --------------------------------------------------------------------------- #
# Amostra mínima para julgar um anúncio como "vencedor" ou "ruim". Abaixo disso
# ele entra como "Em observação" (dado insuficiente) — nunca é classificado só
# porque teve 1 resultado com pouco investimento. Ajuste conforme o ticket/CAC.
SAMPLE_MIN_SPEND = 100.0   # gasto mínimo (R$) para amostra relevante
SAMPLE_MIN_MQLS = 5        # conversas/agendamentos mínimos para julgar um anúncio
TOP_ADS_N = 10             # nº de linhas em Top / Piores anúncios

# Metas & parâmetros da conta (DEFAULTS do painel editável da aba Relatório).
# São só o valor inicial: o usuário edita no navegador (persistido em
# localStorage) e as tabelas de anúncios recoram CPMQL/CAC e reavaliam a
# amostra ao vivo. None = "meta não definida" (métrica aparece sem cor até o
# gestor preencher).
META_CPMQL = None          # meta de CPMQL (R$/MQL); None = não definida
META_CAC = None            # meta de CAC (R$/venda); None = não definida
VOLUME_MIN_AMOSTRAL = SAMPLE_MIN_MQLS  # conversões (MQLs) mínimas p/ amostra confiável
N_DIAS_CORTE = 5           # dias consecutivos acima do teto p/ considerar corte


# --------------------------------------------------------------------------- #
# Leitura
# --------------------------------------------------------------------------- #
def fetch_csv(url: str) -> list[list[str]]:
    req = urllib.request.Request(url, headers={"User-Agent": "dash-template-bot/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        hint = ""
        if e.code in (401, 403):
            hint = (" -> a planilha esta PRIVADA. Compartilhe como 'Qualquer pessoa com o link: Leitor' "
                    "(Compartilhar > Acesso geral) para o build conseguir ler o export CSV.")
        raise SystemExit(f"ERRO ao ler a planilha ({e.code}) {url}{hint}")
    return list(csv.reader(io.StringIO(raw)))


def read_csv_file(path: str) -> list[list[str]]:
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        return list(csv.reader(f))


def load_rows(url: str, local: str | None) -> list[list[str]]:
    return read_csv_file(local) if local else fetch_csv(url)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm(s: str | None) -> str:
    return strip_accents((s or "").strip().lower())


def to_float(v) -> float:
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d,.\-]", "", str(v).strip())
    if not s:
        return 0.0
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_date(v: str) -> str | None:
    if not v:
        return None
    s = str(v).strip()
    if not s:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%d/%m/%y", "%b %d, %Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def is_test_lead(rowtext: str) -> bool:
    return "<test lead" in rowtext.lower()


def is_medico(v: str | None) -> bool:
    """Critério de MQL: coluna "É médico?" (Conversas) / "Médico?" (Leads) == "Sim"."""
    return norm(v) in ("sim", "s", "yes", "true", "1")


def pretty_specialty(v: str) -> str:
    s = (v or "").strip()
    return s if s else "Sem resposta"


def mask_email(e: str) -> str:
    e = (e or "").strip()
    if "@" not in e:
        return "—"
    user, dom = e.split("@", 1)
    keep = user[:2] if len(user) > 2 else user[:1]
    return f"{keep}****@{dom}"


def mask_phone(p: str) -> str:
    digits = re.sub(r"\D", "", p or "")
    return f"…{digits[-4:]}" if len(digits) >= 4 else "—"


def norm_phone(p: str) -> str:
    return re.sub(r"\D", "", p or "")


def canon_phone(p: str) -> str:
    """Chave CANÔNICA de telefone p/ cruzar Compradores × Conversas, robusta às
    3 variações que faziam o mesmo número não bater quando comparado só por
    dígitos (norm_phone):
      - DDI "55" presente de um lado e ausente do outro
        (5511988887777 vs 11988887777);
      - 9º dígito do celular presente/ausente
        (11988887777 vs 1188887777);
      - máscara/espacos/parênteses (já removidos por norm_phone).
    Estratégia: remove o DDI 55 (quando sobra DDD+número) e usa DDD (2 díg.) +
    ÚLTIMOS 8 DÍGITOS — que é o mesmo com ou sem o 9. Devolve chave de 10 díg.
    (DDD+8). Números curtos/estrangeiros (< 10 díg. após limpar) voltam como
    estão, pra não colidir à toa."""
    d = norm_phone(p)
    if len(d) > 11 and d.startswith("55"):
        d = d[2:]            # tira DDI do Brasil, sobrando DDD + local
    if len(d) >= 10:
        return d[:2] + d[-8:]   # DDD + últimos 8 (drop do 9º dígito, se houver)
    return d


def first_last_initial(name: str) -> str:
    parts = (name or "").strip().split()
    if not parts:
        return "—"
    return parts[0] if len(parts) == 1 else f"{parts[0]} {parts[-1][:1]}."


def valid_utm(campaign: str) -> bool:
    c = norm(campaign)
    return bool(c) and c not in ("-", "—", "nao encontrado")


# --------------------------------------------------------------------------- #
# Indexacao das colunas
# --------------------------------------------------------------------------- #
def header_index(header, wanted, fallback):
    idx = {}
    hn = [norm(h) for h in header]
    for key, aliases in wanted.items():
        found = None
        for a in aliases:
            a = norm(a)
            for i, h in enumerate(hn):
                if h == a or (a and a in h):
                    found = i
                    break
            if found is not None:
                break
        idx[key] = found if found is not None else fallback.get(key)
    return idx


def cell(row, i):
    if i is None or i < 0 or i >= len(row):
        return ""
    return (row[i] or "").strip()


# --------------------------------------------------------------------------- #
# Processamento -> registros brutos
# --------------------------------------------------------------------------- #
def name_key(s):
    """Chave de agrupamento de nomes de campanha/conjunto/anúncio: ignora caixa,
    acentos, espaços extras/invisíveis e a diferença entre `_`, `-` e espaço —
    o mesmo anúncio chega da Conversas e do Meta Ads com grafias levemente
    diferentes e, sem isso, vira linhas duplicadas na dash."""
    t = unicodedata.normalize("NFKD", str(s or ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[​-‍﻿]", "", t).casefold()
    return re.sub(r"[\s_\-]+", " ", t).strip()


def unify_names(meta, leads, sales, ad_links):
    """Troca camp/adset/ad por um nome canônico por name_key (preferindo a grafia
    do Meta Ads, que é a do gerenciador) em leads[]/meta[]/sales[]/ad_links."""
    for field in ("camp", "adset", "ad"):
        canon = {}
        for rec in meta + leads + sales:  # meta primeiro => grafia do Meta vence
            v = rec.get(field)
            if v:
                canon.setdefault(name_key(v), re.sub(r"\s+", " ", v).strip())
        for rec in meta + leads + sales:
            v = rec.get(field)
            if v:
                rec[field] = canon[name_key(v)]
        if field == "ad":
            fixed = {}
            for k, link in ad_links.items():
                fixed.setdefault(canon.get(name_key(k), k), link)
            ad_links.clear()
            ad_links.update(fixed)


KOMMO_LEAD_URL = "https://contourculptclinique.kommo.com/leads/detail/"   # abre o lead no CRM (auditoria)
WEEKDAYS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
_RE_PHONE = re.compile(r"^\+?\d{10,13}$")


def kommo_id(link: str) -> str:
    """ID do lead no Kommo = ultimo segmento numerico do link 'Abrir Conversa'.
    Ids curtos (ex. '123', placeholders de teste) sao ignorados."""
    m = re.search(r"/(\d{6,})/?$", (link or "").strip())
    return m.group(1) if m else ""


def clean_name(s: str) -> str:
    """Remove emojis/caracteres exoticos do nome (a coluna Nome vem do WhatsApp)."""
    s = re.sub(r"[^\w\s.\-'À-ÿ]", "", s or "", flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def parse_conv_row(row, idx, ncols):
    """Linha da aba Conversas Iniciadas -> dict. Quando a linha tem o mesmo nº de
    colunas do cabecalho usa o cabecalho; se vier 'deslocada' (celulas vazias
    omitidas), le ANCORADO NA DIREITA (link, status, agendado, telefone, mensagem, nome)."""
    if len(row) == ncols:
        return {"d": cell(row, idx["created"]), "name": cell(row, idx["name"]), "phone": cell(row, idx["phone"]),
                "agendado": cell(row, idx["agendado"]), "status": cell(row, idx["status"]),
                "link": cell(row, idx["link"]), "msg": cell(row, idx["msg"])}
    cells = [(c or "").strip() for c in row]
    out = {"d": cells[0] if cells else "", "name": "", "phone": "", "agendado": "", "status": "", "link": "", "msg": ""}
    rest = cells[1:]
    if rest and rest[-1].lower().startswith("http"):
        out["link"] = rest.pop()
    if rest and norm(rest[-1]) not in ("sim", "nao") and not _RE_PHONE.match(rest[-1]) and re.match(r"^\d\s*\.", rest[-1]):
        out["status"] = rest.pop()
    if rest and norm(rest[-1]) in ("sim", "nao"):
        out["agendado"] = rest.pop()
    if rest and _RE_PHONE.match(rest[-1]):
        out["phone"] = rest.pop()
    if rest:
        out["msg"] = rest.pop()
    if rest:
        cand = rest[-1]
        if not re.fullmatch(r"[0-9a-f\-]{8,}|\d+", cand):
            out["name"] = cand
    return out


def parse_agend_row(row, idx, ncols):
    """Linha da aba Agendamentos (Data, Nome, Telefone, entity_id) -> dict."""
    if len(row) == ncols:
        return {"d": cell(row, idx["date"]), "name": cell(row, idx["name"]),
                "phone": cell(row, idx["phone"]), "entity": cell(row, idx["entity"])}
    cells = [(c or "").strip() for c in row]
    out = {"d": cells[0] if cells else "", "name": "", "phone": "", "entity": ""}
    rest = [c for c in cells[1:] if c]
    for c in list(rest):
        if _RE_PHONE.match(c) and len(c) >= 10:
            out["phone"] = c
            rest.remove(c)
            break
    if rest and re.fullmatch(r"\d{4,}", rest[-1]):
        out["entity"] = rest.pop()
    if rest:
        out["name"] = rest[0]
    return out


def process(conversas_rows, meta_rows, agend_rows, sales_rows):
    # ---------------- Agendamentos ----------------
    aheader = agend_rows[0] if agend_rows else []
    aidx = header_index(aheader, {"date": ["data"], "name": ["nome"], "phone": ["telefone"], "entity": ["entity_id", "entity"]},
                        {"date": 0, "name": 1, "phone": 2, "entity": 3})
    ags = []          # agendamentos unicos: {d, name, phone(canon), entity}
    seen_ag = set()
    for row in agend_rows[1:]:
        if not any((c or "").strip() for c in row):
            continue
        r = parse_agend_row(row, aidx, len(aheader))
        d = parse_date(r["d"].split()[0] if r["d"] else "")
        if not d:
            continue
        key = r["entity"] or canon_phone(r["phone"]) or f"{d}|{r['name']}"
        if key in seen_ag:
            continue
        seen_ag.add(key)
        ags.append({"d": d, "name": r["name"], "phone": canon_phone(r["phone"]), "entity": r["entity"], "used": False})
    ag_by_entity = {a["entity"]: a for a in ags if a["entity"]}
    ag_by_phone = {a["phone"]: a for a in ags if a["phone"]}

    # ---------------- Conversas Iniciadas (leads) ----------------
    cheader = conversas_rows[0] if conversas_rows else []
    cidx = header_index(
        cheader,
        {"created": ["data"], "name": ["nome"], "msg": ["mensagem"], "phone": ["telefone"],
         "agendado": ["agendado"], "status": ["status"], "link": ["abrir conversa", "link"]},
        {"created": 0, "name": 5, "msg": 6, "phone": 7, "agendado": 8, "status": 9, "link": 10},
    )
    leads = []
    seen_conv = {}
    for row in conversas_rows[1:]:
        if not any((c or "").strip() for c in row) or len([c for c in row if (c or "").strip()]) < 3:
            continue
        r = parse_conv_row(row, cidx, len(cheader))
        d = parse_date(r["d"].split()[0] if r["d"] else "")
        if not d:
            continue
        phone = canon_phone(r["phone"])
        kid = kommo_id(r["link"])
        pkey = kid or phone                      # contato unico = 1 conversa (na data da 1a mensagem)
        ag = (ag_by_entity.get(kid) if kid else None) or (ag_by_phone.get(phone) if phone else None)
        if ag:
            ag["used"] = True
        if pkey and pkey in seen_conv:
            prev = seen_conv[pkey]               # repetido: so promove agendamento/consulta
            st2 = r["status"] or ""
            if ag or norm(r["agendado"]) == "sim" or re.search(r"consulta", st2, re.I):
                prev["q"] = 1; prev["plat"] = "Agendado"
            if re.search(r"consulta", st2, re.I):
                prev["c"] = 1; prev["bucket"] = st2
            continue
        status = r["status"] or "Sem status"
        consulta = 1 if re.search(r"consulta", status, re.I) else 0      # etapa "Consulta" do funil
        agendado = bool(ag) or norm(r["agendado"]) == "sim" or bool(consulta)   # quem fez consulta tambem agendou
        dt = datetime.strptime(d, "%Y-%m-%d")
        lead = {
            "d": d,
            "src": "org",                        # CRM nao informa campanha/anuncio
            "plat": "Agendado" if agendado else "Não agendado",
            "camp": "(sem campanha)", "adset": "(sem conjunto)", "ad": "(sem anúncio)",
            "prof": WEEKDAYS[dt.weekday()],      # dia da semana da conversa
            "bucket": status,                    # etapa do funil no Kommo
            "q": 1 if agendado else 0,           # q = AGENDAMENTO (coluna "MQL" do motor)
            "c": consulta,                       # 1 = chegou na etapa Consulta
            "lk": r["link"] if r["link"].startswith("http") else (KOMMO_LEAD_URL + kid if kid else ""),
            "agd": ag["d"] if ag else "",        # data registrada na aba Agendamentos
            "utm": 0,
            "nm": first_last_initial(clean_name(r["name"])),
            "em": "—",
            "ph": mask_phone(r["phone"]),
        }
        leads.append(lead)
        if pkey:
            seen_conv[pkey] = lead
    # agendamentos sem conversa correspondente -> lead extra (data do agendamento)
    n_extra = 0
    for a in ags:
        if a["used"]:
            continue
        n_extra += 1
        leads.append({
            "d": a["d"], "src": "org", "plat": "Agendado",
            "camp": "(sem campanha)", "adset": "(sem conjunto)", "ad": "(sem anúncio)",
            "prof": WEEKDAYS[datetime.strptime(a["d"], "%Y-%m-%d").weekday()],
            "bucket": "Agendado (sem conversa no CRM)", "q": 1, "c": 0, "utm": 0, "x": 1,   # x=1: nao conta como conversa nova
            "lk": (KOMMO_LEAD_URL + a["entity"]) if a["entity"] else "", "agd": a["d"],
            "nm": first_last_initial(clean_name(a["name"])) if a["name"] else "—",
            "em": "—", "ph": mask_phone(a["phone"]),
        })
    print(f"  agendamentos: {len(ags)} unicos · {len(ags) - n_extra} casaram com conversa · "
          f"{n_extra} sem conversa (viraram lead extra)", file=sys.stderr)

    # ---------------- Meta Ads ----------------
    mheader = meta_rows[0] if meta_rows else []
    midx = header_index(
        mheader,
        {"day": ["day", "data"], "campaign": ["campaign name", "campaign"], "adset": ["ad set name", "adset"],
         "ad": ["ad name"], "spent": ["amount spent", "valor gasto", "gasto"], "impr": ["impressions", "impress"],
         "clicks": ["link clicks", "clicks", "cliques"],
         "msgs": ["messaging conversations started", "conversas iniciadas"],
         "pv": ["landing page views", "page views", "pageviews"],
         "chk": ["checkouts initiated", "adds to cart", "initiate checkout"],
         "link": ["creative instagram permalink", "instagram permalink", "permalink",
                  "creative link", "link do anuncio", "link do criativo"]},
        {"day": 0, "campaign": 2, "adset": 3, "ad": 4, "spent": 5, "impr": 6, "clicks": 7, "pv": 8, "msgs": 10},
    )
    meta = []
    ad_links = {}
    for row in meta_rows[1:]:
        if not any((c or "").strip() for c in row) or not parse_date(cell(row, midx["day"])):
            continue
        ad = cell(row, midx["ad"]) or "(sem anúncio)"
        link = cell(row, midx["link"])
        if link and ad not in ad_links:
            ad_links[ad] = link
        meta.append({
            "d": parse_date(cell(row, midx["day"])),
            "camp": cell(row, midx["campaign"]) or "(sem campanha)",
            "adset": cell(row, midx["adset"]) or "(sem conjunto)",
            "ad": ad,
            "sp": round(to_float(cell(row, midx["spent"])), 4),
            "im": to_float(cell(row, midx["impr"])),
            "cl": to_float(cell(row, midx["clicks"])),
            "pv": to_float(cell(row, midx["pv"])),
            "ck": to_float(cell(row, midx["chk"])),
            "ml": to_float(cell(row, midx["msgs"])),   # conversas iniciadas (Meta) = leads por anuncio
        })

    # ---------------- Vendas (FUTURA aba) ----------------
    # Quando GID_SALES existir: colunas esperadas Data · Nome · Telefone · Faturamento · Receita.
    # Sem atribuicao de anuncio (o CRM nao a traz): a venda entra nos totais como "(sem campanha)".
    sales = []
    if sales_rows:
        sheader = sales_rows[0]
        sidx = header_index(sheader, {"date": ["data"], "fat": ["faturamento", "valor"], "receita": ["receita"]},
                            {"date": 0, "fat": 3, "receita": 4})
        for row in sales_rows[1:]:
            if not any((c or "").strip() for c in row):
                continue
            d = parse_date((cell(row, sidx["date"]).split() or [""])[0])
            if not d:
                continue
            fat = to_float(cell(row, sidx["fat"]))
            sales.append({"d": d, "src": "org", "camp": "(sem campanha)", "adset": "(sem conjunto)",
                          "ad": "(sem anúncio)", "vendas": 1, "fat": round(fat, 2),
                          "receita": round(to_float(cell(row, sidx["receita"])) or fat, 2)})

    unify_names(meta, leads, sales, ad_links)

    dates = sorted({d for d in (
        [l["d"] for l in leads if l["d"]] + [m["d"] for m in meta if m["d"]] + [s["d"] for s in sales if s["d"]]
    )})
    now_brt = datetime.now(BRT)
    return {
        "build": {
            "generated_at_brt": now_brt.strftime("%d/%m/%Y %H:%M"),
            "build_id": datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
            "today": now_brt.strftime("%Y-%m-%d"),
            "date_min": dates[0] if dates else None,
            "date_max": dates[-1] if dates else None,
            "tax_factor": TAX_FACTOR,
            "sample_min_spend": SAMPLE_MIN_SPEND,
            "sample_min_mqls": SAMPLE_MIN_MQLS,
            "top_ads_n": TOP_ADS_N,
            "meta_cpmql": META_CPMQL,
            "meta_cac": META_CAC,
            "volume_min_amostral": VOLUME_MIN_AMOSTRAL,
            "n_dias_corte": N_DIAS_CORTE,
            "has_sales": bool(sales_rows),
        },
        "leads": leads,
        "meta": meta,
        "sales": sales,
        "ad_links": ad_links,
        "briefings": {},
    }


# --------------------------------------------------------------------------- #
# Insights de Tráfego (aba Relatório)
# --------------------------------------------------------------------------- #
def load_briefings(path: str) -> dict:
    """Lê build/relatorios.json. Estrutura:
        {"generated_at": "...", "periodos": {"<preset>": {"html": "..."}, ...}}
    Retorna o dict inteiro (ou {} se o arquivo não existir/for inválido).
    A geração NÃO acontece aqui — este build só lê o texto já pronto, sem
    chamar nenhuma API (custo zero no build/no navegador)."""
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {}
    except (ValueError, OSError):
        return {}


# --------------------------------------------------------------------------- #
# Render
# --------------------------------------------------------------------------- #
def render(data, template_path):
    # A dashboard e montada a partir de arquivos separados (visual x logica):
    #   template.html          -> esqueleto HTML (placeholders __STYLES__/__APP_JS__)
    #   identidade-visual.css  -> TODAS as cores (edite aqui p/ mexer so em cor)
    #   estilos.css            -> layout/componentes
    #   app.js                 -> logica + renderizacao
    # Esta funcao so COSTURA os arquivos e injeta os dados; nao altera nada deles.
    base = os.path.dirname(os.path.abspath(template_path))

    def readf(name):
        with open(os.path.join(base, name), "r", encoding="utf-8") as f:
            return f.read()

    with open(template_path, "r", encoding="utf-8") as f:
        tpl = f.read()
    styles = readf("identidade-visual.css") + "\n" + readf("estilos.css")
    tpl = tpl.replace("__STYLES__", styles)
    tpl = tpl.replace("__APP_JS__", readf("app.js"))
    tpl = tpl.replace("__LOGO_B64__", readf("logo_contour.b64").strip())
    tpl = tpl.replace("__DATA_JSON__", json.dumps(data, ensure_ascii=False))
    tpl = tpl.replace("__BUILD_ID__", data["build"]["build_id"])
    tpl = tpl.replace("__GENERATED_BRT__", data["build"]["generated_at_brt"])
    return tpl


def load_sources(conversas_file=None, meta_file=None, agend_file=None, sales_file=None):
    """Le as abas (CSV ao vivo ou arquivos locais p/ teste)."""
    conv = load_rows(EXPORT_URL.format(sid=SPREADSHEET_ID, gid=GID_CONVERSAS), conversas_file)
    meta = load_rows(EXPORT_URL.format(sid=SPREADSHEET_ID, gid=GID_META), meta_file)
    agend = load_rows(EXPORT_URL.format(sid=SPREADSHEET_ID, gid=GID_AGEND), agend_file)
    sales = []
    if sales_file or GID_SALES:
        sales = load_rows(EXPORT_URL.format(sid=SPREADSHEET_ID, gid=GID_SALES), sales_file)
    return conv, meta, agend, sales


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conversas-file", help="CSV local da aba Conversas Iniciadas")
    ap.add_argument("--meta-file", help="CSV local da aba Meta Ads")
    ap.add_argument("--agend-file", help="CSV local da aba Agendamentos")
    ap.add_argument("--sales-file", help="CSV local da (futura) aba de Vendas")
    ap.add_argument("--template", default="build/template.html")
    ap.add_argument("--out", default="dist/index.html")
    args = ap.parse_args()

    conv, meta, agend, sales = load_sources(args.conversas_file, args.meta_file, args.agend_file, args.sales_file)
    data = process(conv, meta, agend, sales)

    briefings_path = os.path.join(os.path.dirname(os.path.abspath(args.template)), "relatorios.json")
    data["briefings"] = load_briefings(briefings_path)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(render(data, args.template))

    b = data["build"]
    ag = sum(l["q"] for l in data["leads"])
    ml = sum(m["ml"] for m in data["meta"])
    sp = sum(m["sp"] for m in data["meta"])
    print("== build ok ==", file=sys.stderr)
    print(f"  periodo   : {b['date_min']} -> {b['date_max']}", file=sys.stderr)
    print(f"  conversas : {len(data['leads'])}  agendamentos: {ag}", file=sys.stderr)
    print(f"  meta ads  : {len(data['meta'])} linhas · gasto R$ {sp:,.2f} · conversas (Meta) {ml:.0f}", file=sys.stderr)
    print(f"  vendas    : {len(data['sales'])} (aba de vendas {'conectada' if b['has_sales'] else 'ainda nao existe'})", file=sys.stderr)
    print(f"  out       : {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
