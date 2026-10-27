#!/usr/bin/env python3
"""
CRO Accelerate — static site builder.

  python build.py              # full build into ./dist (fetches blog posts from WordPress)
  python build.py --offline    # skip WordPress, use only content/posts/*.md

Hosting: GoDaddy (same WordPress hosting, same domain). WordPress keeps running as the blog
editor and REST API; this build produces static pages that GitHub Actions uploads by SFTP into
the WordPress root. Real files/folders are served directly by the web server; everything else
falls through to WordPress, where the mu-plugin redirects old URLs and serves the static home/404.
"""
import argparse
import datetime as dt
import html
import json
import math
import os
import re
import shutil
import sys
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).parent
DIST = ROOT / "dist"
sys.path.insert(0, str(ROOT))
import content as C  # noqa: E402

CFG = json.loads((ROOT / "site.config.json").read_text(encoding="utf-8"))
# environment overrides (GitHub → Settings → Secrets and variables → Actions → Variables)
for key, env in [("gtm_id", "GTM_ID"), ("lead_endpoint", "LEAD_ENDPOINT"), ("wp_api", "WP_API"), ("site_url", "SITE_URL")]:
    if os.environ.get(env):
        CFG[key] = os.environ[env]
if (ROOT / "static/img/oleg.jpg").exists():
    CFG["portrait"] = "/static/img/oleg.jpg"

SITE = CFG["site_url"].rstrip("/")
NOW = dt.datetime.now(dt.timezone.utc)
BUILD_ID = NOW.strftime("%Y%m%d%H%M")

NAV = [
    {"key": "services", "label": "Services", "href": "/services/"},
    {"key": "cases", "label": "Cases", "href": "/cases/"},
    {"key": "ai-office", "label": "AI Office", "href": "/services/ai-office/"},
    {"key": "blog", "label": "Blog", "href": "/blog/"},
    {"key": "about", "label": "About", "href": "/about/"},
    {"key": "contact", "label": "Contact", "href": "/contact/"},
]

env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html"]))

SITEMAP = []  # (path, lastmod, priority)


# ------------------------------------------------------------------ schema helpers
def org_schema():
    return {
        "@context": "https://schema.org",
        "@type": "ProfessionalService",
        "@id": SITE + "/#org",
        "name": CFG["site_name"],
        "url": SITE + "/",
        "logo": SITE + "/static/img/favicon.svg",
        "image": SITE + CFG["default_og_image"],
        "description": "Fractional Chief Innovation Officer services: AI agents, AI offices, live KPI dashboards and revenue systems for scaling companies.",
        "founder": {"@id": SITE + "/#oleg"},
        "areaServed": ["European Union", "United Kingdom", "United States"],
        "email": CFG["email"],
        "sameAs": [CFG["linkedin"]],
        "knowsAbout": ["Artificial intelligence", "AI agents", "Digital transformation", "Business intelligence", "Revenue operations", "Marketing attribution", "ERP"],
    }


def person_schema():
    return {
        "@context": "https://schema.org",
        "@type": "Person",
        "@id": SITE + "/#oleg",
        "name": CFG["owner_name"],
        "jobTitle": CFG["owner_title"],
        "url": SITE + "/about/",
        "sameAs": [CFG["linkedin"]],
        "worksFor": {"@id": SITE + "/#org"},
        **({"image": SITE + CFG["portrait"]} if CFG.get("portrait") else {}),
    }


def website_schema():
    return {"@context": "https://schema.org", "@type": "WebSite", "@id": SITE + "/#website", "url": SITE + "/", "name": CFG["site_name"], "publisher": {"@id": SITE + "/#org"}}


def faq_schema(items):
    return {"@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in items]}


def crumbs_schema(items):
    return {"@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": SITE + p} for i, (n, p) in enumerate(items)]}


# ------------------------------------------------------------------ rendering
def page_ctx(path, title, description, page_type, section="", schema=None, **extra):
    og = extra.pop("og_image", None) or SITE + CFG["default_og_image"]
    if og.startswith("/"):
        og = SITE + og
    return dict(
        title=title, description=description, canonical=SITE + path, page_type=page_type,
        content_group=extra.pop("content_group", page_type), section=section,
        schema=schema or [], og_image=og, **extra,
    )


def write(path, html_text):
    out = DIST / path.lstrip("/")
    if path.endswith("/"):
        out = out / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_text, encoding="utf-8")


def render(template, path, page, priority="0.7", lastmod=None, sitemap=True, **ctx):
    t = env.get_template(template)
    out = t.render(cfg=CFG, nav=NAV, page=page, services=C.SERVICES, cases=C.CASES, icons=C.ICONS,
                   home_faq=C.HOME_FAQ, seams=C.SEAMS, diagrams={'manufacturing-group-control-tower':'From sources to decisions','ai-office-of-agents':'Who talks to whom','multi-entity-finance-automation':'The business objects behind the numbers'}, year=NOW.year, build_id=BUILD_ID, **ctx)
    write(path, out)
    if sitemap and not page.get("noindex"):
        SITEMAP.append((path, lastmod or NOW.date().isoformat(), priority))


# ------------------------------------------------------------------ blog
def slugify(s):
    s = re.sub(r"<[^>]+>", "", s).lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    return re.sub(r"[\s-]+", "-", s).strip("-")[:60] or "section"


def strip_tags(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or "")).replace("\xa0", " ")).strip()


def process_body(body, wp_host, post_slugs=None):
    """add ids to h2 (TOC), lazy images, rewrite internal WP links to /blog/."""
    toc = []
    used = set()

    def h2(m):
        attrs, inner = m.group(1) or "", m.group(2)
        text = strip_tags(inner)
        hid = slugify(text)
        while hid in used:
            hid += "-2"
        used.add(hid)
        toc.append((hid, text))
        attrs = re.sub(r'\sid="[^"]*"', "", attrs)
        return f'<h2 id="{hid}"{attrs}>{inner}</h2>'

    body = re.sub(r"<h2([^>]*)>(.*?)</h2>", h2, body, flags=re.S | re.I)
    body = re.sub(r"<img(?![^>]*loading=)", '<img loading="lazy" decoding="async"', body)
    if wp_host and post_slugs:
        host = re.escape(wp_host.rstrip("/"))

        def relink(m):
            path = m.group(1)
            slug = path.strip("/").split("/")[-1]
            return f'href="/blog/{slug}/"' if slug in post_slugs and not path.startswith("/blog/") else m.group(0)
        # links to other posts (any old permalink shape) -> /blog/<slug>/ ; uploads and pages untouched
        body = re.sub(r'href="(?:' + host + r')?(/(?!wp-content|wp-json|wp-admin)[^"#?]*)"', relink, body)
    body = re.sub(r'<a (href="https?://(?!croaccelerate\.com)[^"]+")', r'<a rel="noopener" target="_blank" \1', body)
    return body, toc


def human_date(iso):
    d = dt.datetime.fromisoformat(iso.replace("Z", "+00:00")[:19])
    return d.strftime("%d %b %Y").lstrip("0")


def fetch_wp():
    import requests
    api = CFG["wp_api"].rstrip("/")
    posts, cats = [], {}
    try:
        r = requests.get(api + "/categories", params={"per_page": 100, "hide_empty": True}, timeout=20)
        r.raise_for_status()
        for c in r.json():
            if c["slug"] != "uncategorized":
                cats[c["id"]] = {"id": c["id"], "slug": c["slug"], "name": html.unescape(c["name"]), "description": strip_tags(c.get("description", ""))}
        page = 1
        while True:
            r = requests.get(api + "/posts", params={"per_page": 50, "page": page, "status": "publish", "_embed": "wp:featuredmedia"}, timeout=30)
            if r.status_code == 400:
                break
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            posts.extend(batch)
            if page >= int(r.headers.get("X-WP-TotalPages", 1)):
                break
            page += 1
    except Exception as e:  # build must never fail because the blog source is down
        print(f"[warn] WordPress fetch failed: {e} — building without WP posts", file=sys.stderr)
        return [], {}

    out = []
    slugs = {p["slug"] for p in posts}
    for p in posts:
        yo = p.get("yoast_head_json") or {}
        media = (p.get("_embedded") or {}).get("wp:featuredmedia") or [{}]
        m0 = media[0] if media else {}
        body, toc = process_body(p["content"]["rendered"], CFG.get("wp_public_host"), slugs)
        words = len(strip_tags(body).split())
        cat_ids = [c for c in p.get("categories", []) if c in cats]
        title = strip_tags(p["title"]["rendered"])
        out.append({
            "slug": p["slug"],
            "title": title,
            "seo_title": (yo.get("title") or f"{title} | {CFG['site_name']}").replace(urlparse(CFG.get("wp_public_host", "")).netloc, "croaccelerate.com"),
            "description": yo.get("description") or strip_tags(p["excerpt"]["rendered"])[:158],
            "excerpt": (strip_tags(p["excerpt"]["rendered"])[:180].rsplit(" ", 1)[0] + "…") if p["excerpt"]["rendered"] else "",
            "html": body, "toc": toc,
            "date": p["date_gmt"] + "Z", "modified": p["modified_gmt"] + "Z",
            "image": m0.get("source_url"), "image_alt": m0.get("alt_text", ""),
            "read_min": max(1, math.ceil(words / 230)),
            "category": cats[cat_ids[0]] if cat_ids else None,
            "old_path": urlparse(p.get("link", "")).path,
            "source": "wp",
        })
    return out, cats


def load_local_posts():
    """content/posts/<slug>.md with a front-matter block between --- lines (key: value)."""
    import markdown
    out = []
    for f in sorted((ROOT / "content/posts").glob("*.md")):
        raw = f.read_text(encoding="utf-8")
        meta, body = {}, raw
        if raw.startswith("---"):
            _, fm, body = raw.split("---", 2)
            for line in fm.strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip().strip('"')
        if meta.get("status", "publish") != "publish":
            continue
        html_body = markdown.markdown(body, extensions=["tables", "fenced_code", "sane_lists"])
        html_body, toc = process_body(html_body, None)
        date = meta.get("date", NOW.date().isoformat()) + "T09:00:00Z"
        words = len(strip_tags(html_body).split())
        title = meta.get("title", f.stem)
        out.append({
            "slug": meta.get("slug", f.stem), "title": title,
            "seo_title": meta.get("seo_title", f"{title} | {CFG['site_name']}"),
            "description": meta.get("description", strip_tags(html_body)[:158]),
            "excerpt": meta.get("excerpt", strip_tags(html_body)[:180].rsplit(" ", 1)[0] + "…"),
            "html": html_body, "toc": toc, "date": date, "modified": meta.get("updated", meta.get("date", "")) and (meta.get("updated", meta.get("date")) + "T09:00:00Z"),
            "image": meta.get("image"), "image_alt": meta.get("image_alt", ""),
            "read_min": max(1, math.ceil(words / 230)), "category": None, "old_path": None, "source": "local",
        })
    return out


def build_blog(posts, cats):
    for p in posts:
        p["date_human"] = human_date(p["date"])
        p["modified_human"] = human_date(p["modified"]) if p.get("modified") else None
    posts.sort(key=lambda p: p["date"], reverse=True)
    per = CFG.get("blog_posts_per_page", 12)

    pages = max(1, math.ceil(len(posts) / per))
    for i in range(pages):
        path = "/blog/" if i == 0 else f"/blog/page/{i + 1}/"
        pager = {"prev": ("/blog/" if i == 1 else f"/blog/page/{i}/") if i > 0 else None,
                 "next": f"/blog/page/{i + 2}/" if i + 1 < pages else None} if pages > 1 else None
        page = page_ctx(path, "Blog — AI, Data & Growth Insights | CRO Accelerate" + (f" (page {i + 1})" if i else ""),
                        "Practical articles on AI agents, AI offices, live KPI dashboards, ERP decisions and B2B revenue systems — from a fractional Chief Innovation Officer.",
                        "blog_index", "blog", schema=[crumbs_schema([("Home", "/"), ("Blog", "/blog/")])], noindex=i > 0)
        render("blog_index.html", path, page, priority="0.8", posts=posts[i * per:(i + 1) * per], pager=pager,
               categories=list(cats.values()), category=None)

    for c in cats.values():
        cp = [p for p in posts if p["category"] and p["category"]["id"] == c["id"]]
        if not cp:
            continue
        path = f"/blog/category/{c['slug']}/"
        page = page_ctx(path, f"{c['name']} — Blog | CRO Accelerate", c["description"] or f"Articles about {c['name']}.", "blog_category", "blog")
        render("blog_index.html", path, page, priority="0.5", posts=cp, pager=None, categories=list(cats.values()), category=c)

    for p in posts:
        path = f"/blog/{p['slug']}/"
        related = [r for r in posts if r is not p and (p["category"] and r["category"] == p["category"])][:3] or [r for r in posts if r is not p][:3]
        article = {
            "@context": "https://schema.org", "@type": "BlogPosting", "headline": p["title"][:110],
            "description": p["description"], "datePublished": p["date"], "dateModified": p.get("modified") or p["date"],
            "author": {"@id": SITE + "/#oleg"}, "publisher": {"@id": SITE + "/#org"},
            "mainEntityOfPage": SITE + path, "image": p["image"] or SITE + CFG["default_og_image"],
        }
        page = page_ctx(path, p["seo_title"], p["description"], "blog_post", "blog",
                        schema=[article, person_schema(), crumbs_schema([("Home", "/"), ("Blog", "/blog/"), (p["title"], path)])],
                        og_type="article", og_image=p["image"], content_group="blog")
        render("blog_post.html", path, page, priority="0.6", lastmod=(p.get("modified") or p["date"])[:10], p=p, related=related)

    # RSS
    items = "".join(
        f"<item><title>{html.escape(p['title'])}</title><link>{SITE}/blog/{p['slug']}/</link><guid>{SITE}/blog/{p['slug']}/</guid>"
        f"<pubDate>{format_datetime(dt.datetime.fromisoformat(p['date'].replace('Z', '+00:00')))}</pubDate>"
        f"<description>{html.escape(p['excerpt'])}</description></item>" for p in posts[:30])
    (DIST / "blog").mkdir(parents=True, exist_ok=True)
    (DIST / "blog/feed.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{CFG["site_name"]} — Blog</title>'
        f"<link>{SITE}/blog/</link><description>AI, data and growth insights</description>{items}</channel></rss>", encoding="utf-8")
    # machine-readable index for the CRO agent
    (DIST / "blog/posts.json").write_text(json.dumps([
        {"slug": p["slug"], "title": p["title"], "url": f"{SITE}/blog/{p['slug']}/", "date": p["date"], "modified": p.get("modified"),
         "category": p["category"]["name"] if p["category"] else None, "words": len(strip_tags(p["html"]).split())} for p in posts], indent=1), encoding="utf-8")


# ------------------------------------------------------------------ pages
SIMPLE_PAGES = {
    "privacy": dict(path="/privacy/", title="Privacy Policy | CRO Accelerate", h1="Privacy policy", crumb="Privacy",
                    desc="How CRO Accelerate collects, uses and protects personal data from this website, contact forms and analytics."),
    "thank-you": dict(path="/thank-you/", title="Thank you | CRO Accelerate", h1="Thank you —", h1_em="message received.", crumb=None,
                      desc="Thank you for getting in touch.", noindex=True, page_type="thank_you"),
}


def build_pages(posts):
    home_schema = [org_schema(), person_schema(), website_schema(), faq_schema(C.HOME_FAQ)]
    render("home.html", "/", page_ctx("/", "Fractional Chief Innovation Officer & AI Agents | CRO Accelerate",
                                      "Oleg Ivanov is a Fractional Chief Innovation Officer for scaling companies in the EU, UK and US: AI strategy, AI agents, AI offices, live KPI dashboards and revenue systems.",
                                      "home", "home", schema=home_schema), priority="1.0", posts=posts)

    render("listing.html", "/services/", page_ctx("/services/", "Services: Fractional CINO, AI Agents | CRO Accelerate",
                                                  "Fractional Chief Innovation Officer, AI agents, chatbots in 2–3 days, AI Office, AI project assistants, Digital Control Tower dashboards and Revenue Engine / Fractional CCO.",
                                                  "services", "services", eyebrow="Services", h1="Services", h1_em="one accountable owner",
                                                  lead="Seven connected services. Start with a diagnostic or a fast build; scale what proves itself.",
                                                  schema=[crumbs_schema([("Home", "/"), ("Services", "/services/")])]), priority="0.9", kind="services")

    for s in C.SERVICES:
        path = f"/services/{s['slug']}/"
        svc = {"@context": "https://schema.org", "@type": "Service", "name": s["name"], "description": s["seo_desc"],
               "provider": {"@id": SITE + "/#org"}, "areaServed": ["European Union", "United Kingdom", "United States"], "url": SITE + path}
        related_map = {
            "fractional-chief-innovation-officer": ["manufacturing-group-control-tower", "ai-office-of-agents"],
            "ai-agents": ["ai-office-of-agents", "closed-loop-marketing-attribution"],
            "chatbots": ["ai-office-of-agents", "market-intelligence-eu-expansion"],
            "ai-office": ["ai-office-of-agents", "manufacturing-group-control-tower"],
            "project-assistants": ["manufacturing-group-control-tower", "multi-entity-finance-automation"],
            "digital-control-tower": ["manufacturing-group-control-tower", "multi-entity-finance-automation"],
            "revenue-engine": ["closed-loop-marketing-attribution", "market-intelligence-eu-expansion"]}
        by_slug = {c["slug"]: c for c in C.CASES}
        related = [by_slug[x] for x in related_map.get(s["slug"], []) if x in by_slug] or C.CASES[:2]
        render("service.html", path, page_ctx(path, s["seo_title"], s["seo_desc"], "service", "ai-office" if s["slug"] == "ai-office" else "services",
                                              schema=[svc, faq_schema(s["faq"]), crumbs_schema([("Home", "/"), ("Services", "/services/"), (s["short"], path)])],
                                              content_group="service"), priority="0.9", s=s, related=related)

    render("listing.html", "/cases/", page_ctx("/cases/", "Case Studies: AI, Data & Revenue | CRO Accelerate",
                                               "Anonymised case studies: live management dashboards, a multi-agent AI Office, closed-loop marketing attribution, multi-entity finance automation and market intelligence for EU expansion.",
                                               "cases", "cases", eyebrow="Cases", h1="Case studies", h1_em="built from zero",
                                               lead="Five anonymised stories — from scaling a multi-site manufacturing group to running our own AI Office. The same playbook we bring to clients.",
                                               schema=[crumbs_schema([("Home", "/"), ("Cases", "/cases/")])]), priority="0.9", kind="cases")
    for c in C.CASES:
        path = f"/cases/{c['slug']}/"
        art = {"@context": "https://schema.org", "@type": "Article", "headline": c["title"][:110], "description": c["seo_desc"],
               "author": {"@id": SITE + "/#oleg"}, "publisher": {"@id": SITE + "/#org"}, "mainEntityOfPage": SITE + path}
        render("case.html", path, page_ctx(path, c["seo_title"], c["seo_desc"], "case", "cases",
                                           schema=[art, crumbs_schema([("Home", "/"), ("Cases", "/cases/"), (c["short"], path)])], content_group="case"),
               priority="0.8", c=c, others=[o for o in C.CASES if o is not c][:2])

    render("about.html", "/about/", page_ctx("/about/", "About Oleg Ivanov & Team | CRO Accelerate",
                                             "20+ years in technology and B2B growth: IT services business development, CCO and COO/CRO roles, and co-founder & CINO of a manufacturing group.",
                                             "about", "about", schema=[person_schema(), crumbs_schema([("Home", "/"), ("About", "/about/")])]), priority="0.7")
    render("contact.html", "/contact/", page_ctx("/contact/", "Contact & Book a Call | CRO Accelerate",
                                                 "Book a 30-minute call or send a message about AI agents, an AI Office, live KPI dashboards or revenue systems. Reply within one business day.",
                                                 "contact", "contact"), priority="0.8")
    render("ai_readiness.html", "/ai-readiness/", page_ctx("/ai-readiness/", "AI Readiness Scorecard (Free, 4 Minutes) | CRO Accelerate",
                                                           "Free AI & digital readiness assessment for mid-market companies: 12 questions across strategy, data, automation and people, with a personal 90-day roadmap.",
                                                           "lead_magnet", "", content_group="lead_magnet"), priority="0.9")

    for key, sp in SIMPLE_PAGES.items():
        body = (ROOT / f"content/pages/{key}.html").read_text(encoding="utf-8")
        body = body.replace("{{EMAIL}}", CFG["email"]).replace("{{UPDATED}}", NOW.strftime("%d %B %Y"))
        render("simple.html", sp["path"], page_ctx(sp["path"], sp["title"], sp["desc"], sp.get("page_type", key), "",
                                                   noindex=sp.get("noindex", False), h1=sp["h1"], h1_em=sp.get("h1_em"), crumb=sp.get("crumb")),
               priority="0.3", body=body, sitemap=not sp.get("noindex"))

    nf = env.get_template("simple.html").render(
        cfg=CFG, nav=NAV, cases=C.CASES, year=NOW.year, build_id=BUILD_ID,
        page=page_ctx("/404", "Page not found | CRO Accelerate", "Page not found.", "404", "", noindex=True, h1="This page", h1_em="moved or never existed.", crumb=None),
        body='<p class="lead">The site was rebuilt in 2026 — some old addresses changed.</p><div class="btn-row"><a class="btn btn-primary" href="/">Go home →</a><a class="btn btn-glass" href="/services/">Services</a><a class="btn btn-glass" href="/blog/">Blog</a></div>')
    (DIST / "404.html").write_text(nf, encoding="utf-8")


# ------------------------------------------------------------------ technical SEO files
def build_tech(posts):
    urls = "".join(f"<url><loc>{SITE}{p}</loc><lastmod>{lm}</lastmod><priority>{pr}</priority></url>" for p, lm, pr in SITEMAP)
    (DIST / "sitemap.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>', encoding="utf-8")
    (DIST / "robots.txt").write_text(f"User-agent: *\nAllow: /\nDisallow: /thank-you/\n\nSitemap: {SITE}/sitemap.xml\n", encoding="utf-8")

    redirects = (ROOT / "static_root/_redirects").read_text(encoding="utf-8").rstrip() + "\n\n# --- old WordPress post URLs -> /blog/ (generated)\n"
    own = {p for p, _, _ in SITEMAP}
    for p in posts:
        old = p.get("old_path")
        if old and old not in own and not old.startswith("/blog/") and old != "/":
            redirects += f"{old} /blog/{p['slug']}/ 301\n"
    (DIST / "_redirects").write_text(redirects, encoding="utf-8")
    # same map as JSON for the WordPress mu-plugin (GoDaddy hosting does not read _redirects)
    rmap = {}
    for line in redirects.splitlines():
        parts = line.split()
        if len(parts) >= 2 and not line.startswith("#") and "*" not in parts[0] and parts[1].startswith("/"):
            rmap[parts[0].rstrip("/") + "/"] = parts[1]
    (DIST / "redirects.json").write_text(json.dumps(rmap, indent=1), encoding="utf-8")
    shutil.copy(ROOT / "static_root/_headers", DIST / "_headers")
    for f in (ROOT / "static_root").glob("*"):
        if f.name not in ("_redirects", "_headers"):
            shutil.copy(f, DIST / f.name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()
    shutil.copytree(ROOT / "static", DIST / "static")

    posts, cats = ([], {}) if args.offline or os.environ.get("BLOG_OFFLINE") else fetch_wp()
    posts += load_local_posts()
    build_blog(posts, cats)
    build_pages(posts)
    build_tech(posts)
    print(f"Built {len(SITEMAP)} indexable pages, {len(posts)} posts → {DIST}  (build {BUILD_ID})")


if __name__ == "__main__":
    main()
