"""Downloads today's UCSC dining hall menus and writes menu.json.
Written without sight of the site's HTML. If it finds nothing, it saves the raw pages to debug/."""
import json, re, sys, time, pathlib, datetime
from zoneinfo import ZoneInfo
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

BASE = "https://nutrition.sa.ucsc.edu/"
HALLS = {
    "Colleges Nine & Ten": ["nine", "lewis", "college ten"],
    "Cowell & Stevenson": ["cowell", "stevenson"],
    "Crown & Merrill": ["crown", "merrill"],
    "Porter & Kresge": ["porter", "kresge"],
    "Rachel Carson & Oakes": ["carson", "oakes"],
}
MEALS = ["Breakfast", "Lunch", "Dinner", "Late Night"]
http = requests.Session()
http.headers["User-Agent"] = "personal-macro-planner (one run per day)"
debug, cache = pathlib.Path("debug"), {}

def get(url):
    time.sleep(0.3)
    r = http.get(url, timeout=30, verify=False)
    r.raise_for_status()
    return r.text

def dump(name, html):
    debug.mkdir(exist_ok=True)
    (debug / name).write_text(html, encoding="utf-8")

def anchors(soup, base, key):
    return [(a.get_text(" ", strip=True), urljoin(base, a["href"]))
            for a in soup.find_all("a", href=True) if key in a["href"].lower()]

def grab(text, label):
    m = re.search(label + r"\D{0,15}?(\d+(?:\.\d+)?)\s*g", text, re.I)
    return float(m.group(1)) if m else None

def nutrition(url):
    if url not in cache:
        try:
            t = BeautifulSoup(get(url), "html.parser").get_text(" ", strip=True)
            s = re.search(r"Serving Size:?\s*(.{1,30}?)\s+(?:Calories|Amount|Servings)", t, re.I)
            cache[url] = (grab(t, "Protein"), grab(t, r"Total Carb\w*"), grab(t, "Total Fat"),
                          s.group(1) if s else "1 serving")
        except Exception as e:
            print("label failed", url, e)
            cache[url] = (None,) * 4
    return cache[url]

def meal_name(text):
    return next((m for m in MEALS if m.lower() in text.lower()), None)

def scrape_page(url, hall, meal, items, seen):
    soup, cur = BeautifulSoup(get(url), "html.parser"), meal
    for tag in soup.find_all(True):
        txt = tag.get_text(" ", strip=True)
        if tag.name != "a" and not tag.find(True) and txt.title() in MEALS:
            cur = txt.title()
        href = tag.get("href", "") if tag.name == "a" else ""
        if cur and "label" in href.lower() and "recnum" in href.lower():
            if (hall, cur, txt) in seen:
                continue
            seen.add((hall, cur, txt))
            p, c, f, serv = nutrition(urljoin(url, href))
            if None not in (p, c, f):
                items.append({"hall": hall, "meal": cur, "name": txt, "serv": serv, "p": p, "c": c, "f": f})
    return soup

def main():
    home = get(BASE)
    dump("home.html", home)
    locs = anchors(BeautifulSoup(home, "html.parser"), BASE, "locationnum")
    items, seen = [], set()
    for hall, keys in HALLS.items():
        url = next((u for n, u in locs if any(k in (n + " " + u).lower() for k in keys)), None)
        if not url:
            print("no link found for", hall)
            continue
        soup = scrape_page(url, hall, None, items, seen)
        dump(hall.split()[0] + ".html", str(soup))
        for text, u in anchors(soup, url, "mealname"):
            if meal_name(text):
                scrape_page(u, hall, meal_name(text), items, seen)
    if not items:
        print("No items parsed. Raw pages saved in debug/.")
        sys.exit(1)
    stamp = datetime.datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%b %d, %Y")
    pathlib.Path("menu.json").write_text(json.dumps({"updated": stamp, "items": items}))
    print(len(items), "items saved")

main()
