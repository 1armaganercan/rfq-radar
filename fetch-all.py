#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Çok kaynaklı RFQ fetcher  ->  site/rfq.json
===========================================
Kaynaklar (hepsi ücretsiz, sunucu tarafı):
  * TED (AB)         — anahtarsız API
  * CanadaBuys (CA)  — anahtarsız açık CSV
  * SAM.gov (US)     — ücretsiz API anahtarı (env: SAM_API_KEY); NAICS ile filtreler

Her kayıt aynı şemaya yazılır ve KAYNAK etiketlenir:
  id, date, source, region, category, title, buyer, value, deadline, url

GitHub Actions her gün çalıştırır; çıktı site/rfq.json -> Pages'te sayfa okur.
Yerelde test: pip install requests; SAM için: export SAM_API_KEY=...; python fetch_all.py
"""

import os, json, csv, io, time, datetime as dt
import requests

# ===================== CONFIG =====================
DAYS_BACK = 7
OUT = "site/rfq.json"

# --- TED ---
TED_ENDPOINT = "https://api.ted.europa.eu/v3/notices/search"
TED_COUNTRIES = ["DEU","AUT","CZE","SVK","HUN","POL","ROU","ITA","FRA","NLD","SWE"]  # alpha-3
TED_CPV = ["42000000","44500000","44400000","44200000","44210000"]
TED_FIELDS_SAFE = ["publication-number","notice-title","buyer-name","notice-type"]
TED_FIELDS_EXTRA = ["publication-date","deadline-receipt-request","classification-cpv","buyer-country"]

# --- CanadaBuys ---
CB_CSV = "https://canadabuys.canada.ca/opendata/pub/openTenderNotice-ouvertAvisAppelOffres.csv"
CB_CATEGORIES = {"GD","SRVTGD"}   # mal + mala bağlı hizmet (talaşlı/döküm buralarda)

# --- SAM.gov ---
SAM_ENDPOINT = "https://api.sam.gov/prod/opportunities/v2/search"
SAM_KEY = os.environ.get("SAM_API_KEY", "")
SAM_NAICS = ["332710", "331510", "331520"]   # machine shops, ferrous/nonferrous foundries

# --- sınıflandırma ---
KW_CASTING = ["casting","castings","cast iron","ductile iron","grey iron","gray iron",
  "investment casting","sand casting","die casting","foundry",
  "gussteil","gusseisen","sphäroguss","fonderie","moulage"," fonte","getti","ghisa",
  "odlitek","odlitky","liatina","döküm","sfero"]
KW_MACHINING = ["machined part","machined parts","machined component","turned part","milled part",
  "precision machined","subcontract machining","contract machining","cnc machining of",
  "machining of parts","drehteil","frästeil","zerspanung","pièce usinée","pièces usinées",
  "particolare meccanico","işlenmiş parça","talaşlı imal","talaşlı işle"]
# tezgâh/ekipman ALIMI sinyalleri -> bunlar geçerse ele (TED'i batıran gürültü)
KW_EXCLUDE = ["machine tool","machine tools","machining centre","machining center",
  "milling machine","drilling machine","grinding machine","lathe machine","cnc lathe",
  "cnc machine","cnc milling","boring machine","sawing machine","press brake","laser cutter",
  "laserschneider","werkzeugmaschine","drehmaschine","fräsmaschine","schleifmaschine",
  "bohrmaschine","soustruh","frézka","obráběcí stroj","centre d'usinage","centres d'usinage",
  "fraiseuse","tour à commande","tornio","fresatrice","alesatrice","macchina utensile",
  "tezgah","tezgâh"]

def classify(text):
    t = (text or "").lower()
    if any(k in t for k in KW_EXCLUDE): return None      # tezgâh alımı -> ele
    if any(k in t for k in KW_CASTING): return "casting"
    if any(k in t for k in KW_MACHINING): return "machining"
    return None

def norm_date(s):
    s = (s or "").strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-": return s[:10]
    if len(s) >= 10 and s[2] == "/" and s[5] == "/":     # mm/dd/yyyy
        return f"{s[6:10]}-{s[0:2]}-{s[3:5]}"
    if len(s) >= 8 and s[:8].isdigit(): return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return ""

def first(d, *keys, default=""):
    for k in keys:
        if k in d and d[k] not in (None,"",[],{}):
            v = d[k]
            if isinstance(v, list): v = v[0] if v else ""
            if isinstance(v, dict): v = v.get("eng") or v.get("en") or next(iter(v.values()), "")
            return str(v).strip()
    return default

# ===================== TED =====================
def ted_query():
    df = (dt.date.today() - dt.timedelta(days=DAYS_BACK)).strftime("%Y%m%d")
    return (f"classification-cpv IN ({' '.join(TED_CPV)}) "
            f"AND buyer-country IN ({' '.join(TED_COUNTRIES)}) "
            f"AND contract-nature IN (supplies) AND notice-type IN (cn-standard) "
            f"AND publication-date >= {df}")

def ted_fetch(query, page, fields, limit=100):
    body = {"query":query,"fields":fields,"page":page,"limit":limit,"scope":"ACTIVE",
            "paginationMode":"PAGE_NUMBER","checkQuerySyntax":False}
    r = requests.post(TED_ENDPOINT, json=body, timeout=40,
                      headers={"Accept":"application/json","Content-Type":"application/json"})
    if r.status_code != 200: raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
    return r.json()

def ted():
    rows = []
    try:
        q = ted_query()
        fields = list(TED_FIELDS_SAFE)
        for f in TED_FIELDS_EXTRA:
            try: ted_fetch(q,1,fields+[f],1); fields.append(f)
            except RuntimeError: pass
            time.sleep(0.5)
        for page in range(1,6):
            data = ted_fetch(q,page,fields)
            res = data.get("notices") or data.get("results") or []
            if not res: break
            for it in res:
                pub = first(it,"publication-number","ND")
                title = first(it,"notice-title","TI",default="")
                cpv = first(it,"classification-cpv",default="")
                cat = classify(title+" "+cpv)
                if not pub or not cat: continue
                country = first(it,"buyer-country","CY",default="")
                rows.append({"id":"ted-"+pub,"date":norm_date(first(it,"publication-date","PD")),
                    "source":"TED","region":country or "EU","category":cat,"title":title,
                    "buyer":first(it,"buyer-name",default=country),"value":"",
                    "deadline":norm_date(first(it,"deadline-receipt-request")),
                    "url":f"https://ted.europa.eu/en/notice/-/detail/{pub}"})
            if len(res) < 100: break
            time.sleep(1.0)
    except Exception as e:
        print("TED hata:", e)
    print(f"TED: {len(rows)} ilgili")
    return rows

# ===================== CanadaBuys =====================
def cb_col(header, *needles):
    for h in header:
        hl = h.lower()
        if all(n in hl for n in needles): return h
    return None

def canadabuys():
    rows = []
    try:
        ua = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
        r = requests.get(CB_CSV, timeout=90,
                         headers={"User-Agent": ua, "Accept": "text/csv,*/*"})
        r.raise_for_status()
        rd = csv.DictReader(io.StringIO(r.content.decode("utf-8-sig", errors="replace")))
        header = rd.fieldnames or []
        c_title = cb_col(header,"title","eng") or cb_col(header,"title")
        c_desc  = cb_col(header,"description","eng")
        c_cat   = cb_col(header,"procurementcategory")
        c_pub   = cb_col(header,"publicationdate")
        c_close = cb_col(header,"closingdate") or cb_col(header,"tenderclosing")
        c_url   = cb_col(header,"noticeurl","eng") or cb_col(header,"noticeurl")
        c_buyer = cb_col(header,"contactinfoname") or cb_col(header,"enduser") or cb_col(header,"organization")
        c_ref   = cb_col(header,"referencenumber") or cb_col(header,"solicitationnumber")
        cutoff = (dt.date.today() - dt.timedelta(days=DAYS_BACK)).isoformat()
        for row in rd:
            cat_field = (row.get(c_cat,"") if c_cat else "")
            if CB_CATEGORIES and cat_field and not (set(cat_field.replace(" ","").split(",")) & CB_CATEGORIES):
                continue
            title = (row.get(c_title,"") if c_title else "").strip()
            desc  = (row.get(c_desc,"") if c_desc else "")
            cat = classify(title+" "+desc)
            if not cat: continue
            pub = norm_date(row.get(c_pub,"") if c_pub else "")
            if pub and pub < cutoff: continue
            ref = (row.get(c_ref,"") if c_ref else "") or title[:24]
            rows.append({"id":"cb-"+ref.strip().replace(" ","")[:24],"date":pub,
                "source":"CanadaBuys","region":"CA","category":cat,"title":title,
                "buyer":(row.get(c_buyer,"") if c_buyer else "").strip(),"value":"",
                "deadline":norm_date(row.get(c_close,"") if c_close else ""),
                "url":(row.get(c_url,"") if c_url else "").strip()})
    except Exception as e:
        print("CanadaBuys hata:", e)
    print(f"CanadaBuys: {len(rows)} ilgili")
    return rows

# ===================== SAM.gov =====================
def sam():
    rows = []
    if not SAM_KEY:
        print("SAM.gov: anahtar yok (SAM_API_KEY), atlandı"); return rows
    pf = (dt.date.today()-dt.timedelta(days=DAYS_BACK)).strftime("%m/%d/%Y")
    pt = dt.date.today().strftime("%m/%d/%Y")
    for naics in SAM_NAICS:
        try:
            params = {"api_key":SAM_KEY,"postedFrom":pf,"postedTo":pt,"limit":"1000",
                      "offset":"0","ptype":"o","ncode":naics}
            r = requests.get(SAM_ENDPOINT, params=params, timeout=60,
                             headers={"Accept":"application/json"})
            if r.status_code != 200:
                print(f"SAM {naics}: HTTP {r.status_code} {r.text[:150]}"); continue
            for o in r.json().get("opportunitiesData", []):
                title = o.get("title","")
                # NAICS zaten talaşlı/dökümü garantiliyor; tezgâh-alımı kelimesi geçerse yine ele
                cat = "casting" if naics.startswith("3315") else "machining"
                if any(k in title.lower() for k in KW_EXCLUDE): continue
                pop = (o.get("placeOfPerformance") or {})
                rows.append({"id":"sam-"+str(o.get("noticeId") or o.get("solicitationNumber") or title[:20]),
                    "date":norm_date(o.get("postedDate","")),"source":"SAM.gov",
                    "region":(pop.get("country") or {}).get("code","US") if isinstance(pop.get("country"),dict) else "US",
                    "category":cat,"title":title,
                    "buyer":o.get("fullParentPathName") or o.get("organizationName",""),"value":"",
                    "deadline":norm_date(o.get("responseDeadLine","")),
                    "url":o.get("uiLink","")})
        except Exception as e:
            print(f"SAM {naics} hata:", e)
        time.sleep(1.0)
    print(f"SAM.gov: {len(rows)} ilgili")
    return rows

# ===================== merge & write =====================
def main():
    all_rows = ted() + canadabuys() + sam()
    seen, merged = set(), []
    for r in all_rows:
        if r["id"] in seen: continue
        seen.add(r["id"]); merged.append(r)
    merged.sort(key=lambda r: r.get("date",""), reverse=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    payload = {"updated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
               "count": len(merged), "rows": merged}
    with open(OUT,"w",encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\nToplam {len(merged)} ilgili RFQ -> {OUT}")

if __name__ == "__main__":
    main()
