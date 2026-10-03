"""Pipeline de prospection : CSV -> (scraping du site) -> maquette -> brouillon Thunderbird, un prospect à la fois.

Usage :
  python prospect_pipeline.py prospects.csv              # boucle interactive, un prospect à la fois
  python prospect_pipeline.py prospects.csv --only "DS Caruso"
  python prospect_pipeline.py prospects.csv --prepare-only   # prépare tout (scraping + maquettes) sans rien ouvrir
  python prospect_pipeline.py prospects.csv --list

Colonnes du CSV (les accents / majuscules n'importent pas ; seuls nom + email sont obligatoires) :
  nom ; ville ; telephone ; email ; activite ; site_web ; contact ; civilite ; statut
- activite : ex. « plombier chauffagiste », « restaurant tapas », « coiffeur » (sert à choisir le thème et le texte du mail)
- site_web : laisser vide si l'entreprise n'a pas de site
- contact  : NOM DE FAMILLE du dirigeant, uniquement si tu en es sûr (sinon le mail commence par « Bonjour, »)
- statut   : rempli automatiquement (vide -> prêt -> brouillon -> envoyé / ignoré)
"""
import argparse
import asyncio
import csv
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
import urllib.parse
import urllib.request
from datetime import date

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

from generate_mockup import PROFILES, THEMES, logo_color, mix, render_from_file, theme_name  # noqa: E402

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
ALIASES = {
    "nom": "nom", "entreprise": "nom", "societe": "nom", "raison_sociale": "nom", "name": "nom",
    "ville": "ville", "city": "ville", "localisation": "ville",
    "telephone": "telephone", "tel": "telephone", "phone": "telephone", "mobile": "telephone",
    "email": "email", "mail": "email", "courriel": "email", "e-mail": "email",
    "activite": "activite", "metier": "activite", "secteur": "activite", "categorie": "activite",
    "site_web": "site_web", "site": "site_web", "website": "site_web", "url": "site_web", "web": "site_web",
    "contact": "contact", "nom_contact": "contact", "dirigeant": "contact", "nom_dirigeant": "contact",
    "accroche": "accroche", "titre": "accroche", "sous_titre": "sous_titre", "soustitre": "sous_titre",
    "service_1": "service_1", "service_2": "service_2", "service_3": "service_3", "service_4": "service_4",
    "civilite": "civilite", "statut": "statut", "status": "statut", "date_envoi": "date_envoi",
}
SKIP_HEADS = re.compile(r"contact|propos|avis|témoign|temoign|menu|newsletter|suivez|horaire|mentions|copyright|cookie|"
                        r"en savoir|^services$|réseaux|reseaux|partenaire|footer|accueil|bienvenue|faq|^nos |^notre |^pourquoi|^ils |^vos |^un problème|^prêt|^besoin|^votre |^découvrez|^demandez", re.I)
SKIP_IMG = re.compile(r"logo|icon|sprite|avatar|flag|favicon|placeholder|pixel|payment|badge|partner|\.svg|\.gif|emoji|"
                      r"facebook|instagram|twitter|linkedin|google|trustpilot|pattern|texture", re.I)


# ---------------------------------------------------------------- utilitaires
def norm(text: str) -> str:
    text = unicodedata.normalize("NFD", (text or "").lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", norm(text)).strip("-") or "prospect"


def clip(text: str, n: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(" ", 1)[0].rstrip(",;:- ")
    return cut + "…" if not cut.endswith(".") else cut


def fetch(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def google_font_ok(family: str) -> bool:
    try:
        url = "https://fonts.googleapis.com/css2?family=" + urllib.parse.quote(family).replace("%20", "+") + ":wght@400;700"
        fetch(url, 10)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- CSV
def read_csv(path: str):
    with open(path, encoding="utf-8-sig", newline="") as f:
        raw = f.read()
    first = raw.splitlines()[0] if raw else ""
    delim = max([",", ";", "\t"], key=first.count)
    reader = csv.reader(io.StringIO(raw), delimiter=delim)
    header = next(reader)
    cols = [ALIASES.get(re.sub(r"[\s-]+", "_", norm(h).strip()), re.sub(r"\s+", "_", norm(h).strip())) for h in header]
    rows = [dict(zip(cols, [c.strip() for c in r])) for r in reader if any(c.strip() for c in r)]
    for extra in ("statut", "date_envoi"):
        if extra not in cols:
            cols.append(extra)
    return rows, cols, delim


def write_csv(path: str, rows, cols, delim):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=delim, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------- scraping (Playwright : gère les sites JS)
JS_EXTRACT = r"""
() => {
  const abs = u => { try { return new URL(u, location.href).href } catch (e) { return null } };
  const txt = e => (e.innerText || '').replace(/\s+/g, ' ').trim();
  const meta = n => (document.querySelector(`meta[name="${n}"],meta[property="${n}"]`) || {}).content || '';
  const cn = e => (typeof e.className === 'string' ? e.className : (e.className && e.className.baseVal) || '');
  const imgs = [];
  document.querySelectorAll('img').forEach(i => {
    const src = i.currentSrc || i.src; if (!src || src.startsWith('data:')) return;
    const r = i.getBoundingClientRect();
    imgs.push({src: abs(src), w: i.naturalWidth, h: i.naturalHeight, alt: i.alt || '', cls: cn(i), id: i.id || '', rw: r.width, rh: r.height});
  });
  document.querySelectorAll('section,div,header,figure,a,li').forEach(e => {
    const bg = getComputedStyle(e).backgroundImage;
    if (bg && bg.startsWith('url(')) {
      const m = bg.match(/url\(["']?(.*?)["']?\)/); const r = e.getBoundingClientRect();
      if (m && !m[1].startsWith('data:') && r.width > 300 && r.height > 180)
        imgs.push({src: abs(m[1]), w: Math.round(r.width * 1.5), h: Math.round(r.height * 1.5), alt: '', cls: 'bg', id: '', rw: r.width, rh: r.height, bg: true});
    }
  });
  let lg = [...document.querySelectorAll('img')].find(i => /logo/i.test((i.src || '') + (i.alt || '') + cn(i) + i.id))
        || document.querySelector('header img, nav img, [class*=navbar] img, [class*=header] img')
        || document.querySelector('[class*=logo] svg, header svg');
  if (lg) lg.setAttribute('data-pp-logo', '1');
  const heads = [];
  document.querySelectorAll('h2,h3').forEach(h => {
    const t = txt(h); if (t.length < 6 || t.length > 70) return;
    let p = '', n = h.nextElementSibling;
    for (let k = 0; k < 3 && n && !p; k++, n = n.nextElementSibling) {
      const x = txt(n); if (x.length > 30 && x.length < 320) p = x;
    }
    heads.push({t, p});
  });
  const h1 = document.querySelector('h1');
  const fam = e => ((e && getComputedStyle(e).fontFamily) || '').split(',')[0].replace(/["']/g, '').trim();
  const btn = [];
  document.querySelectorAll('a[class*=btn],a[class*=button],button,[class*=btn],[class*=cta]').forEach(b => btn.push(getComputedStyle(b).backgroundColor));
  const links = a => [...document.querySelectorAll(a)].map(x => x.getAttribute('href'));
  return {logoSrc: (lg && lg.tagName === 'IMG') ? (lg.currentSrc || lg.src) : '', title: document.title, desc: meta('description') || meta('og:description'), h1: h1 ? txt(h1) : '',
          heads, imgs, hasLogo: !!lg, hfont: fam(h1 || document.querySelector('h2')), bfont: fam(document.body), btn,
          tel: links('a[href^="tel:"]'), mail: links('a[href^="mailto:"]'), ogimg: abs(meta('og:image')) || '',
          icons: [...document.querySelectorAll('link[rel*=icon]')].map(l => ({h: abs(l.href), s: l.sizes ? l.sizes.value : ''}))};
}
"""


def scrape_site(url: str, out_dir: str) -> dict:
    """Ouvre le site dans Chromium, récupère textes / couleurs / polices / photos / logo. Ne plante jamais : renvoie {} en cas d'échec."""
    from playwright.sync_api import sync_playwright
    from PIL import Image
    os.makedirs(out_dir, exist_ok=True)
    result = {"photos": [], "logo": "", "heads": [], "desc": "", "h1": "", "colors": [], "hfont": "", "bfont": ""}
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": 1440, "height": 900}, user_agent=UA)
            try:
                pg.goto(url, wait_until="networkidle", timeout=25000)
            except Exception:  # site lent / requêtes qui ne se terminent jamais : on repart sur le DOM déjà chargé
                try:
                    pg.goto(url, wait_until="domcontentloaded", timeout=40000)
                    pg.wait_for_timeout(4000)
                except Exception:
                    pass
            height = min(pg.evaluate("document.body.scrollHeight"), 20000)
            for y in range(0, height, 600):  # déclenche le chargement paresseux
                pg.evaluate(f"window.scrollTo(0,{y})")
                pg.wait_for_timeout(200)
            pg.evaluate("window.scrollTo(0,0)")
            pg.wait_for_timeout(500)
            info = pg.evaluate(JS_EXTRACT)
            # logo : capture de l'élément (fonctionne aussi pour les SVG)
            if info.get("hasLogo"):
                try:
                    dest = os.path.join(out_dir, "logo.png")
                    src = info.get("logoSrc") or ""
                    if src.startswith("http") and not src.lower().split("?")[0].endswith(".svg"):
                        try:  # fichier d'origine (évite les logos rognés par leur conteneur)
                            im = Image.open(io.BytesIO(fetch(src, 15))).convert("RGBA")
                            if im.width >= 40 and im.height >= 20:
                                im.save(dest)
                                result["logo"] = dest
                        except Exception:
                            pass
                    if not result["logo"]:
                        pg.locator("[data-pp-logo]").first.screenshot(path=dest, omit_background=True, timeout=8000)
                    im = Image.open(dest)
                    if im.width >= 40 and im.height >= 20:
                        result["logo"] = dest
                except Exception:
                    pass
            b.close()
    except Exception as e:
        print(f"   ! navigateur : {e.__class__.__name__}, tentative en lecture simple …")
        return scrape_static(url, out_dir, result)
    if not info.get("imgs") and not info.get("heads"):
        print("   ! page vide dans le navigateur, tentative en lecture simple …")
        return scrape_static(url, out_dir, result)

    result.update(desc=info.get("desc", ""), h1=info.get("h1", ""), heads=info.get("heads", []),
                  hfont=info.get("hfont", ""), bfont=info.get("bfont", ""),
                  tel=info.get("tel", []), mail=info.get("mail", []))
    # logo de secours : favicon la plus grande
    if not result["logo"]:
        best = None
        for ic in info.get("icons", []):
            m = re.match(r"(\d+)", ic.get("s") or "")
            size = int(m.group(1)) if m else 0
            if ic.get("h") and (best is None or size > best[0]):
                best = (size, ic["h"])
        if best and not best[1].endswith(".svg"):
            try:
                dest = os.path.join(out_dir, "logo.png")
                Image.open(io.BytesIO(fetch(best[1]))).convert("RGBA").save(dest)
                result["logo"] = dest if Image.open(dest).width >= 48 else ""
            except Exception:
                pass
    # couleurs des boutons du site (saturées uniquement)
    import colorsys
    cols = {}
    for c in info.get("btn", []):
        m = re.match(r"rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?", c or "")
        if not m or (m.group(4) is not None and float(m.group(4)) < .5):
            continue
        r, g, bl = (int(m.group(i)) for i in (1, 2, 3))
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, bl / 255)
        if s > .35 and .25 < v < .95:
            cols["#%02x%02x%02x" % (r, g, bl)] = cols.get("#%02x%02x%02x" % (r, g, bl), 0) + 1
    result["colors"] = sorted(cols, key=cols.get, reverse=True)

    # photos
    cands, seen = [], set()
    for im in info.get("imgs", []):
        src = im.get("src") or ""
        if not src.startswith("http") or SKIP_IMG.search(src + " " + im.get("alt", "") + " " + im.get("cls", "")) and not im.get("bg"):
            continue
        w = max(im.get("w") or 0, int((im.get("rw") or 0) * 2))  # tailles affichées x2 : les sites responsive servent de petites versions
        h = max(im.get("h") or 0, int((im.get("rh") or 0) * 2))
        if w < 380 or h < 300 or not (.5 <= w / max(h, 1) <= 4):
            continue
        stem = re.sub(r"-\d+x\d+(?=\.\w+$)", "", os.path.basename(urllib.parse.urlparse(src).path).lower())
        if stem in seen:
            continue
        seen.add(stem)
        cands.append((w * h, src))
    if info.get("ogimg") and info["ogimg"] not in [c[1] for c in cands]:
        cands.append((1, info["ogimg"]))
    cands.sort(reverse=True)
    hashes, got = set(), []
    for _, src in cands[:14]:
        try:
            data = None
            if "?" in src:  # version d'origine (sans paramètres de redimensionnement), sinon la version affichée
                try:
                    data = fetch(src.split("?")[0])
                    Image.open(io.BytesIO(data))
                except Exception:
                    data = None
            data = data or fetch(src)
            h = hashlib.md5(data).hexdigest()
            im = Image.open(io.BytesIO(data))
            if h in hashes or im.width < 380 or im.height < 300:
                continue
            hashes.add(h)
            dest = os.path.join(out_dir, f"photo_{len(got) + 1}.jpg")
            im.convert("RGB").save(dest, quality=90)
            got.append((im.width * im.height, dest))
        except Exception:
            continue
        if len(got) >= 4:
            break
    result["photos"] = [d for _, d in sorted(got, reverse=True)]
    return result


SECTOR_ICONS = {"batiment": ["wrench", "droplet", "bolt", "home"], "bois": ["hammer", "ruler", "leaf", "home"],
                "nature": ["leaf", "sun", "droplet", "heart"], "gastro": ["utensils", "glass", "flame", "star"],
                "beaute": ["scissors", "heart", "sparkle", "leaf"], "auto": ["car", "wrench", "bolt", "shield"],
                "default": ["sparkle", "shield", "home", "star"]}


def scrape_static(url: str, out_dir: str, result: dict) -> dict:
    """Plan B (site qui bloque / fait expirer Chromium) : lecture du HTML brut, sans JavaScript."""
    import html as htmllib
    from PIL import Image
    try:
        page = fetch(url).decode("utf-8", "ignore")
    except Exception as e:
        print(f"   ! lecture simple impossible aussi ({e.__class__.__name__})")
        return result
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", page, flags=re.S)
    meta = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', page, re.I | re.S)
    result["desc"] = htmllib.unescape(meta.group(1)).strip() if meta else ""
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.S | re.I)
    result["h1"] = htmllib.unescape(re.sub(r"<[^>]+>", " ", h1.group(1))).strip() if h1 else ""
    heads = []
    for m in re.finditer(r"<h[23][^>]*>(.*?)</h[23]>\s*(?:<[^p][^>]*>\s*)*<p[^>]*>(.*?)</p>", body, re.S | re.I):
        t, para = (htmllib.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x))).strip() for x in m.groups())
        if 6 <= len(t) <= 70 and 30 < len(para) < 320:
            heads.append({"t": t, "p": para})
    result["heads"] = heads
    seen, got = set(), []
    for src in re.findall(r"<img[^>]+src=[\"']([^\"']+)[\"']", body, re.I):
        src = urllib.parse.urljoin(url, src)
        stem = re.sub(r"-\d+x\d+(?=\.\w+$)", "", os.path.basename(urllib.parse.urlparse(src).path).lower())
        if SKIP_IMG.search(src) or stem in seen or not re.search(r"\.(jpe?g|png|webp)", src, re.I):
            continue
        seen.add(stem)
        try:
            im = Image.open(io.BytesIO(fetch(src, 15)))
            if im.width >= 380 and im.height >= 300 and .5 <= im.width / im.height <= 4:
                dest = os.path.join(out_dir, f"photo_{len(got) + 1}.jpg")
                im.convert("RGB").save(dest, quality=90)
                got.append((im.width * im.height, dest))
        except Exception:
            continue
    result["photos"] = [d for _, d in sorted(got, reverse=True)[:4]]
    return result


def placeholder_images(theme: dict, out_dir: str, n: int, tname: str = "default", activite: str = "") -> list:
    """Visuels de marque (dégradé aux couleurs du logo + grille + grande icône du métier) quand le site n'a aucune photo."""
    from playwright.sync_api import sync_playwright
    from generate_mockup import ICONS
    icons = list(SECTOR_ICONS.get(tname, SECTOR_ICONS["default"]))
    if "serrur" in norm(activite):
        icons = ["key", "shield", "home", "wrench"]
    dark = mix(theme["text"], "#000000", .45)
    paths = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1600, "height": 1000})
        for i in range(n):
            d = ICONS.get(icons[i % len(icons)], ICONS["sparkle"])
            x, y = [(62, 40), (38, 58), (70, 62), (48, 36)][i % 4]
            html = f"""<body style="margin:0;width:1600px;height:1000px;overflow:hidden;position:relative;
              background:radial-gradient(900px 700px at {x}% {y}%, {mix(theme['accent'], dark, .35)}, transparent 70%),
                         linear-gradient({120 + i * 35}deg, {mix(theme['accent'], dark, .62)}, {dark})">
              <div style="position:absolute;inset:0;background-image:linear-gradient(rgba(255,255,255,.07) 1px,transparent 1px),
                 linear-gradient(90deg,rgba(255,255,255,.07) 1px,transparent 1px);background-size:64px 64px"></div>
              <svg viewBox="0 0 24 24" width="640" height="640" fill="none" stroke="rgba(255,255,255,.22)" stroke-width=".7"
                 stroke-linecap="round" stroke-linejoin="round" style="position:absolute;left:{x}%;top:{y}%;transform:translate(-50%,-50%) rotate({(-12, 8, -6, 14)[i % 4]}deg)">
                 <path d="{d}"/></svg></body>"""
            pg.set_content(html)
            dest = os.path.join(out_dir, f"visuel_{i + 1}.jpg")
            pg.screenshot(path=dest, type="jpeg", quality=90)
            paths.append(dest)
        b.close()
    return paths


# ---------------------------------------------------------------- construction du JSON prospect
def build_prospect(row: dict, folder: str) -> dict:
    img_dir = os.path.join(folder, "images")
    os.makedirs(img_dir, exist_ok=True)
    brand = row["nom"]
    city = row.get("ville", "")
    activite = row.get("activite", "")
    site = row.get("site_web", "").strip()
    if site and not site.startswith("http"):
        site = "https://" + site

    probe = {"BRAND_NAME": brand, "BADGE_TEXT": activite, "HERO_TITLE": activite, "HERO_SUBTITLE": ""}
    tname = theme_name(probe)
    theme = THEMES[tname]
    prof = PROFILES.get(tname, PROFILES["default"])

    web = {"photos": [], "logo": "", "heads": [], "desc": "", "h1": "", "colors": [], "hfont": "", "bfont": ""}
    if site:
        print(f"   → lecture du site {site} …")
        web = scrape_site(site, img_dir)
        print(f"     {len(web['photos'])} photo(s), logo : {'oui' if web['logo'] else 'non'}, {len(web['heads'])} titre(s) de section")

    # photos : site -> dossier stock/<thème>/ -> visuels de remplacement
    photos = list(web["photos"])
    stock = sorted(p for ext in ("jpg", "jpeg", "png", "webp") for p in
                   __import__("glob").glob(os.path.join("stock", tname, f"*.{ext}")))
    if len(photos) < 4 and stock:
        photos += stock[:4 - len(photos)]
    fallback_used = False
    if len(photos) < 4:  # complète avec des visuels de marque plutôt que de répéter la même photo
        accent = (web["colors"] or [theme["accent"]])[0]
        if web["logo"]:
            accent = logo_color(web["logo"]) or accent
        extra = placeholder_images({**theme, "accent": accent}, img_dir, 4, tname, activite)
        photos += extra[len(photos):4]
        fallback_used = not web["photos"] and not stock
    hero, real, fin, atel = photos[:4]

    # textes : sections du site sinon contenu par défaut du métier
    PHONE = re.compile(r"\d{2}[ .]\d{2}[ .]\d{2}|@|www\.|https?:")
    JUNK = re.compile(r"voir aussi|cliquez|lire la suite|en savoir|disponible 24|appelez|©", re.I)
    def tidy(t):
        t = t.strip()
        return t.capitalize() if t.isupper() else t
    heads = [dict(t=tidy(h["t"]), p=h["p"]) for h in web["heads"]
             if h["p"] and not SKIP_HEADS.search(h["t"]) and not PHONE.search(h["t"] + h["p"]) and not JUNK.search(h["p"])
             and norm(brand) not in norm(h["t"]) and norm(h["t"]) not in norm(brand)]
    fallback_items = prof["p4"]["items"]
    titles, descs = [], []
    for i in range(3):
        if i < len(heads):
            titles.append(clip(heads[i]["t"], 55))
            descs.append(clip(heads[i]["p"], 150))
        else:
            titles.append(fallback_items[i][0])
            descs.append(fallback_items[i][2])

    # colonnes facultatives du CSV : « Titre | description » pour service_1..3 (service_4 = 4e carte)
    for i in range(3):
        raw = (row.get(f"service_{i + 1}") or "").strip()
        if raw:
            t, _, d_ = raw.partition("|")
            titles[i] = clip(t, 55)
            if d_.strip():
                descs[i] = clip(d_, 150)
    where = f" à {city}" if city else ""
    h1 = web["h1"].strip()
    if row.get("accroche"):
        hero_title = row["accroche"].strip()
    elif 18 <= len(h1) <= 90 and norm(h1) != norm(brand):
        hero_title = h1
    else:
        hero_title = f"{activite.capitalize()}{where} : un service sur mesure, près de chez vous." if activite else f"{brand}, votre partenaire de confiance{where}."
    subtitle = row.get("sous_titre") or (clip(web["desc"], 170) if len(web["desc"]) > 40 else (
        f"{activite.capitalize()}{where}. Contactez-nous pour échanger sur votre projet." if activite else "Contactez-nous pour échanger sur votre projet."))

    data = {
        "BRAND_NAME": brand,
        "CITY": city,
        "EMAIL": row["email"],
        "PHONE": row.get("telephone", ""),
        "BADGE_TEXT": f"{activite} — {city}" if activite and city else (activite or brand),
        "HERO_TITLE": hero_title,
        "HERO_SUBTITLE": subtitle,
        "SOURCE_SITE_URL": site,
        "SECTEUR": tname,
        "RECHERCHE": f"« {activite} »" if activite else "des professionnels de votre secteur",
        "CONFIGURATEUR": tname not in ("gastro", "beaute"),
        "CALL_LABEL": "Appeler",
        "HERO_IMG": hero, "IMG_REALISATION": real, "IMG_FINITION": fin, "IMG_ATELIER": atel,
        "TITLE_IMG_2": titles[0], "DESC_IMG_2": descs[0],
        "TITLE_IMG_3": titles[1], "DESC_IMG_3": descs[1],
        "TITLE_IMG_4": titles[2], "DESC_IMG_4": descs[2],
        "OUTPUT_DIR": os.path.join(folder, "maquette"),
        "_fallback_images": fallback_used,
    }
    if web["logo"]:
        data["LOGO"] = web["logo"]
    last = row.get("contact", "").strip()
    if last:
        data["CONTACT_LASTNAME"] = last
        if row.get("civilite"):
            data["CONTACT_CIVILITY"] = row["civilite"]

    # « design du site » : couleur d'accent (si pas de logo) + polices reprises si disponibles sur Google Fonts
    style = {}
    if not web["logo"] and web["colors"]:
        style["accent"] = web["colors"][0]
        style["soft"] = mix(web["colors"][0], theme["bg"], .85)
    for key, fam in (("heading_font", web["hfont"]), ("body_font", web["bfont"])):
        if fam and fam.lower() not in ("arial", "helvetica", "sans-serif", "serif", "system-ui", "times new roman", "georgia") and google_font_ok(fam):
            style[key] = fam
    if style:
        data["THEME"] = style
    return data


# ---------------------------------------------------------------- étapes
def prepare(row: dict) -> str:
    folder = os.path.join("prospects", slugify(row["nom"]))
    os.makedirs(folder, exist_ok=True)
    jpath = os.path.join(folder, "prospect.json")
    data = build_prospect(row, folder)
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    render(jpath)
    return jpath


def render(jpath: str):
    print("   → génération de la maquette …")
    asyncio.run(render_from_file(jpath))


def open_draft(jpath: str):
    subprocess.run([sys.executable, "send_draft.py", jpath], check=False)


def show(row):
    print("\n" + "=" * 70)
    print(f"{row['nom']}  —  {row.get('activite', '?')}  —  {row.get('ville', '?')}")
    print(f"   {row['email']}  {row.get('telephone', '')}   site : {row.get('site_web') or '(aucun)'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv")
    ap.add_argument("--only", help="Ne traiter que ce prospect (nom exact ou partie du nom)")
    ap.add_argument("--prepare-only", action="store_true", help="Prépare maquettes + JSON pour tous, sans ouvrir de brouillon")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    rows, cols, delim = read_csv(args.csv)
    if args.list:
        for r in rows:
            print(f"{(r.get('statut') or 'à faire'):10} {r.get('nom', '?'):30} {r.get('ville', ''):20} {r.get('email', '')}")
        return

    def save():
        write_csv(args.csv, rows, cols, delim)

    todo = [r for r in rows if (r.get("statut") or "").lower() in ("", "prêt", "pret", "brouillon")]
    if args.only:
        todo = [r for r in rows if norm(args.only) in norm(r.get("nom", ""))]
    print(f"{len(todo)} prospect(s) à traiter.")

    for i, row in enumerate(todo, 1):
        if not row.get("nom") or not re.match(r"[^@\s]+@[^@\s]+\.\w+", row.get("email", "")):
            print(f"\n[{row.get('nom', '?')}] pas d'e-mail valide : ignoré.")
            continue
        show(row)
        print(f"   ({i}/{len(todo)})")
        jpath = os.path.join("prospects", slugify(row["nom"]), "prospect.json")
        if not os.path.isfile(jpath) or (row.get("statut") or "") == "":
            jpath = prepare(row)
            row["statut"] = "prêt"
            save()
        data = json.load(open(jpath, encoding="utf-8"))
        if data.get("_fallback_images"):
            print("   ⚠ aucune photo trouvée : visuels génériques utilisés. Ajoute des photos dans "
                  f"stock/{data['SECTEUR']}/ ou dans {os.path.dirname(jpath)}/images/ puis édite le JSON.")
        print(f"   Maquettes : {data['OUTPUT_DIR']}/     Réglages : {jpath}")
        if args.prepare_only:
            continue

        while True:
            choice = input("\n [d] ouvrir le brouillon dans Thunderbird   [r] régénérer (après édition du JSON)\n"
                           " [s] passer (ignoré)   [n] suivant sans rien changer   [q] quitter  > ").strip().lower()
            if choice == "r":
                render(jpath)
            elif choice == "d":
                open_draft(jpath)
                row["statut"] = "brouillon"
                save()
                if input(" Envoyé depuis Thunderbird ? [o/N] ").strip().lower() == "o":
                    row["statut"] = "envoyé"
                    row["date_envoi"] = date.today().isoformat()
                    save()
                    break
            elif choice == "s":
                row["statut"] = "ignoré"
                save()
                break
            elif choice == "n":
                break
            elif choice == "q":
                save()
                return
    print("\nTerminé.")


if __name__ == "__main__":
    main()
