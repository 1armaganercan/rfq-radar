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

import os, json, csv, io, time, re, datetime as dt
import requests

# ===================== CONFIG =====================
DAYS_BACK = 7
OUT = "site/rfq.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

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
# NAICS -> kategori. 6 haneli kodlar. "machining" = genel metal-işleme kovası
# (talaşlı + sac + kesim + dövme + pres + yapısal); "casting" = dökümhane/die-cast.
# Panelde şimdilik iki çip var (TALAŞLI/DÖKÜM); ayrı SAC/DÖVME çipi istersen sonra ekleriz.
SAM_NAICS = {
  # MFG-01 CNC & Hassas İşleme
  "332710":"CNC & Hassas İşleme","332721":"CNC & Hassas İşleme",
  # MFG-02 Sac İşleme
  "332322":"Sac İşleme","332313":"Sac İşleme","332114":"Sac İşleme",
  # MFG-03 Kaynak & Çelik Konstrüksiyon
  "332312":"Kaynak & Çelik Konstrüksiyon","332311":"Kaynak & Çelik Konstrüksiyon","332323":"Kaynak & Çelik Konstrüksiyon",
  # MFG-04 Döküm & Foundry
  "331511":"Döküm & Foundry","331512":"Döküm & Foundry","331513":"Döküm & Foundry",
  "331523":"Döküm & Foundry","331524":"Döküm & Foundry","331529":"Döküm & Foundry",
  # MFG-05 Dövme & Şekillendirme (+ pres/stamping)
  "332111":"Dövme & Şekillendirme","332112":"Dövme & Şekillendirme",
  "332117":"Dövme & Şekillendirme","332119":"Dövme & Şekillendirme",
  # MFG-06 Bağlantı Elemanları
  "332722":"Bağlantı Elemanları","332510":"Bağlantı Elemanları","332618":"Bağlantı Elemanları",
  # MFG-07 Plastik & Kauçuk
  "326199":"Plastik & Kauçuk","326220":"Plastik & Kauçuk","326291":"Plastik & Kauçuk","326122":"Plastik & Kauçuk",
  # MFG-08 Yüzey İşlem & Kaplama
  "332812":"Yüzey İşlem & Kaplama","332813":"Yüzey İşlem & Kaplama",
  # MFG-09 Montaj & Muhtelif İmalat
  "332999":"Montaj & Muhtelif İmalat",
  # MFG-10 Endüstriyel Komponent (valf/fitting/rulman/boru/profil)
  "332911":"Endüstriyel Komponent","332912":"Endüstriyel Komponent","332919":"Endüstriyel Komponent",
  "332991":"Endüstriyel Komponent","332996":"Endüstriyel Komponent",
  "331210":"Endüstriyel Komponent","331221":"Endüstriyel Komponent",
  # MFG-12 Makine/Otomotiv/Demiryolu Parça
  "336510":"Makine/Otomotiv/Demiryolu Parça","336370":"Makine/Otomotiv/Demiryolu Parça","336390":"Makine/Otomotiv/Demiryolu Parça",
  # MFG-14 Ambalaj & Konteyner
  "332431":"Ambalaj & Konteyner","332439":"Ambalaj & Konteyner",
  # Dişli & Tahrik (gear making)
  "333612":"Dişli & Tahrik",
}

# --- sınıflandırma ---
KW_CASTING = [
  # EN
  "casting","castings","cast iron","ductile iron","grey iron","gray iron","cast steel",
  "investment casting","sand casting","die casting","foundry","cast part",
  # DE / FR / IT / NL / SE
  "guss","gussteil","gusseisen","sphäroguss","gießerei","gegossen",
  "fonderie","moulage"," fonte","pièce moulée","coulée",
  "fonderia","fusione","ghisa","getti","getto di",
  "gietwerk","gietstuk","gietijzer","gjutgods","gjutning","gjutjärn",
  # CZ / PL / RO
  "odlitek","odlitky","slévárna","litina","odlew","odlewy","odlewnia","żeliwo",
  "turnare","turnat","fontă","piese turnate",
  # TR
  "döküm","pik döküm","sfero"]

KW_MACHINING = [
  # EN — talaşlı + sac + kaynak + dövme + kesim + yapısal
  "machined","machining","cnc","turned","milled","milling","turning",
  "fabricated","fabrication","sheet metal","sheet-metal","weldment","welded","welding",
  "forged","forging","stamping","stamped","laser cutting","plasma cutting","waterjet",
  "bending","structural steel","steel structure","steel fabrication","metal part","metal parts",
  "machined part","machined component","turned part","milled part","precision machined",
  # DE
  "zerspanung","gefräst","gedreht","drehteil","frästeil","blech","blechteil","blechbearbeitung",
  "schweiß","geschweißt","schweißbaugruppe","biegen","laserschneiden","stahlbau","metallbau",
  "schmiedeteil","gestanzt","stanzteil",
  # FR
  "usinage","usiné","fraisage","tournage","tôle","tôlerie","soudure","soudé","soudage",
  "découpe laser","pliage","charpente métallique","pièce métallique","pièce usinée","pièces usinées",
  "forgé","emboutissage",
  # IT
  "lavorazione meccanica","tornitura","fresatura","lamiera","carpenteria metallica","saldatura",
  "saldato","taglio laser","piegatura","particolare meccanico","stampaggio","forgiato",
  # CZ / PL / RO / NL / SE
  "obrábění","frézování","soustružení","plech","svařování","svařovaný","ohýbání",
  "ocelová konstrukce","výpalky",
  "obróbka","frezowanie","toczenie","blacha","spawanie","spawane","gięcie",
  "konstrukcja stalowa","wycinanie laserowe","tłoczenie","kucie",
  "prelucrare","frezare","strunjire","tablă","sudură","sudat","debitare laser","îndoire",
  "structură metalică","ștanțare","forjare","confecții metalice",
  "verspaning","gefreesd","gedraaid","plaatwerk","lassen","gelast","staalconstructie","gesmeed",
  "bearbetning","fräsning","svarvning","plåt","svetsning","svetsad","laserskärning","stålkonstruktion","smide",
  # TR
  "talaşlı","işlenmiş","torna","freze","sac","kaynak","kaynaklı","lazer kesim","büküm",
  "çelik konstrüksiyon","dövme","pres parça","sac metal",
  # dişli / su jeti / boru-profil (çok dilli)
  "gear","gears","gear cutting","zahnrad","engrenage","ingranagg","dişli",
  "water jet","waterjet","wasserstrahl","jet d'eau","su jeti",
  "pipe","pipes","tube","tubes","tubing","rohr","tuyau","tubo","trubka","rura","boru","profil"]

# tezgâh/ekipman ALIMI sinyalleri -> bunlar geçerse ele (önce kontrol edilir, makine satın almayı eler)
KW_EXCLUDE = [
  "machine tool","machine tools","machining centre","machining center","milling machine",
  "drilling machine","grinding machine","lathe machine","cnc lathe","cnc machine","cnc milling",
  "boring machine","sawing machine","press brake","laser cutter","laser cutting machine",
  "welding machine","bending machine","stamping press","forging press","induction furnace",
  # DE
  "werkzeugmaschine","drehmaschine","fräsmaschine","schleifmaschine","bohrmaschine",
  "sägemaschine","laserschneidmaschine","schweißgerät","biegemaschine","abkantpresse",
  # FR / IT
  "machine-outil","tour à commande","fraiseuse","perceuse","rectifieuse","presse plieuse",
  "machine de découpe","poste à souder","centre d'usinage","centres d'usinage",
  "macchina utensile","tornio","fresatrice","alesatrice","rettificatrice","pressa piegatrice",
  "saldatrice",
  # CZ / PL / RO / NL / SE
  "obráběcí stroj","soustruh","frézka","bruska","ohraňovací lis","svářečka",
  "obrabiarka","tokarka","frezarka","szlifierka","prasa krawędziowa","spawarka",
  "mașină-unealtă","strung","mașină de găurit","aparat de sudură",
  "gereedschapsmachine","draaibank","freesmachine","lasapparaat",
  "verktygsmaskin","svarv","fräsmaskin","svetsmaskin",
  # TR
  "tezgah","tezgâh","torna tezgah","freze tezgah","cnc tezgah","kaynak makinesi"]

def classify(text):
    t = (text or "").lower()
    if any(k in t for k in KW_EXCLUDE): return None      # tezgâh alımı -> ele
    if any(k in t for k in KW_CASTING): return "Döküm & Foundry"
    if any(k in t for k in KW_MACHINING): return "CNC & Hassas İşleme"
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
    hdr = {"Accept":"application/json","Content-Type":"application/json","User-Agent":UA}
    for attempt in range(2):
        r = requests.post(TED_ENDPOINT, json=body, timeout=40, headers=hdr)
        if r.status_code == 200: return r.json()
        if r.status_code in (403, 429) and attempt == 0:
            time.sleep(6); continue
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")

def ted():
    rows = []; raw = 0
    try:
        q = ted_query()
        fields = TED_FIELDS_SAFE + TED_FIELDS_EXTRA
        for page in range(1,6):
            data = ted_fetch(q,page,fields)
            res = data.get("notices") or data.get("results") or []
            if not res: break
            raw += len(res)
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
    print(f"TED: ham {raw}, ilgili {len(rows)}")
    return rows

# ===================== CanadaBuys =====================
def cb_col(header, *needles):
    for h in header:
        hl = h.lower()
        if all(n in hl for n in needles): return h
    return None

def canadabuys():
    rows = []; total = 0
    try:
        ua = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
        r = requests.get(CB_CSV, timeout=90,
                         headers={"User-Agent": ua, "Accept": "text/csv,*/*"})
        r.raise_for_status()
        rd = csv.DictReader(io.StringIO(r.content.decode("utf-8-sig", errors="replace")))
        header = rd.fieldnames or []
        c_title = cb_col(header,"title","eng") or cb_col(header,"title")
        c_desc  = cb_col(header,"tenderdescription","eng") or cb_col(header,"description","eng")
        c_gsin  = cb_col(header,"gsindescription","eng")
        c_cat   = cb_col(header,"procurementcategory")
        c_pub   = cb_col(header,"publicationdate")
        c_close = cb_col(header,"closingdate") or cb_col(header,"tenderclosing")
        c_url   = cb_col(header,"noticeurl","eng") or cb_col(header,"noticeurl")
        c_buyer = cb_col(header,"contactinfoname") or cb_col(header,"enduser") or cb_col(header,"organization")
        c_ref   = cb_col(header,"referencenumber") or cb_col(header,"solicitationnumber")
        print(f"  CB sütunlar: title={c_title} | desc={c_desc} | gsin={c_gsin} | close={c_close} | url={c_url}")
        for row in rd:
            total += 1
            title = (row.get(c_title,"") if c_title else "").strip()
            desc  = (row.get(c_desc,"") if c_desc else "")
            gsin  = (row.get(c_gsin,"") if c_gsin else "")
            cat = classify(title+" "+desc+" "+gsin)
            if not cat: continue
            pub = norm_date(row.get(c_pub,"") if c_pub else "")
            ref = (row.get(c_ref,"") if c_ref else "") or title[:24]
            rows.append({"id":"cb-"+ref.strip().replace(" ","")[:24],"date":pub,
                "source":"CanadaBuys","region":"CA","category":cat,"title":title,
                "buyer":(row.get(c_buyer,"") if c_buyer else "").strip(),"value":"",
                "deadline":norm_date(row.get(c_close,"") if c_close else ""),
                "url":(row.get(c_url,"") if c_url else "").strip()})
    except Exception as e:
        print("CanadaBuys hata:", e)
    print(f"CanadaBuys: {total} satır tarandı, {len(rows)} ilgili")
    return rows

# ===================== SAM.gov =====================
def sam():
    rows = []
    if not SAM_KEY:
        print("SAM.gov: anahtar yok (SAM_API_KEY), atlandı"); return rows
    pf = (dt.date.today()-dt.timedelta(days=DAYS_BACK)).strftime("%m/%d/%Y")
    pt = dt.date.today().strftime("%m/%d/%Y")
    offset, calls = 0, 0
    while calls < 6:                      # 6 istek <= 10/gün limiti
        try:
            params = {"api_key":SAM_KEY,"postedFrom":pf,"postedTo":pt,
                      "limit":"1000","offset":str(offset)}   # ptype yok = tüm tipler
            r = requests.get(SAM_ENDPOINT, params=params, timeout=60,
                             headers={"Accept":"application/json"})
            calls += 1
            if r.status_code != 200:
                print(f"SAM HTTP {r.status_code}: {r.text[:150]}"); break
            items = r.json().get("opportunitiesData", [])
            if not items: break
            for o in items:
                typ = o.get("type") or ""
                if "Award" in typ or "Justification" in typ: continue
                naics = str(o.get("naicsCode") or "")
                if not naics:
                    nl = o.get("naics") or o.get("naicsCodes")
                    if isinstance(nl, list) and nl:
                        naics = str(nl[0].get("code") if isinstance(nl[0], dict) else nl[0])
                cat = SAM_NAICS.get(naics)
                if not cat: continue                       # NAICS setimizde değilse atla
                title = o.get("title","")
                if any(k in title.lower() for k in KW_EXCLUDE): continue
                pop = o.get("placeOfPerformance") or {}
                c = pop.get("country") if isinstance(pop, dict) else None
                country = (c.get("code") if isinstance(c, dict) else c) or "US"
                rows.append({"id":"sam-"+str(o.get("noticeId") or o.get("solicitationNumber") or title[:20]),
                    "date":norm_date(o.get("postedDate","")),"source":"SAM.gov","region":country,
                    "category":cat,"title":title,
                    "buyer":o.get("fullParentPathName") or o.get("organizationName",""),"value":"",
                    "deadline":norm_date(o.get("responseDeadLine","")),"url":o.get("uiLink","")})
            if len(items) < 1000: break
            offset += 1000; time.sleep(1.0)
        except Exception as e:
            print("SAM hata:", e); break
    print(f"SAM.gov: {len(rows)} ilgili")
    return rows

# ===================== merge & write =====================
def norm_title(t):
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()[:70]

def main():
    all_rows = ted() + canadabuys() + sam()
    seen_id, seen_title, merged, dups = set(), set(), [], 0
    for r in all_rows:
        if r["id"] in seen_id: continue
        nt = norm_title(r.get("title"))
        if nt and nt in seen_title:          # aynı RFQ farklı kaynakta -> tek tut
            dups += 1; continue
        seen_id.add(r["id"])
        if nt: seen_title.add(nt)
        merged.append(r)
    if dups: print(f"dedup: {dups} tekrar elendi")
    merged.sort(key=lambda r: r.get("date",""), reverse=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    payload = {"updated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
               "count": len(merged), "rows": merged}
    with open(OUT,"w",encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\nToplam {len(merged)} ilgili RFQ -> {OUT}")

if __name__ == "__main__":
    main()
