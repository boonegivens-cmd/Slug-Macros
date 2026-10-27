"""Downloads today's UCSC dining hall menus and writes menu.json."""
import json, re, sys, time, pathlib, datetime
from zoneinfo import ZoneInfo
from urllib.parse import urljoin, urlparse, parse_qs
import requests
from bs4 import BeautifulSoup

BASE = "https://nutrition.sa.ucsc.edu/"
HALLS = {
    "College Nine & John R. Lewis": ["nine", "lewis", "college ten"],
    "Cowell & Stevenson": ["cowell", "stevenson"],
    "Crown & Merrill": ["crown", "merrill"],
    "Porter & Kresge": ["porter", "kresge"],
    "Rachel Carson & Oakes": ["carson", "oakes"],
}
MEALS = ["Breakfast", "Lunch", "Dinner", "Late Night"]
http = requests.Session()
http.verify = False  # the site's certificate chain is incomplete
requests.packages.urllib3.disable_warnings()
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

def meal_from_url(u):
    m = parse_qs(urlparse(u).query).get("mealName", [""])[0]
    return next((x for x in MEALS if x.lower() == m.lower()), None)

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

def scrape_meal(url, hall, meal, items, seen):
    soup = BeautifulSoup(get(url), "html.parser")
    for a in soup.find_all("a", href=True):
        if "label.aspx" not in a["href"].lower():
            continue
        name = a.get_text(" ", strip=True)
        if not name or (hall, meal, name) in seen:
            continue
        seen.add((hall, meal, name))
        p, c, f, serv = nutrition(urljoin(url, a["href"]))
        if None not in (p, c, f):
            items.append({"hall": hall, "meal": meal, "name": name, "serv": serv, "p": p, "c": c, "f": f})
    return str(soup)

def main():
    home = get(BASE)
    locs = anchors(BeautifulSoup(home, "html.parser"), BASE, "locationnum")
    items, seen = [], set()
    for hall, keys in HALLS.items():
        url = next((u for n, u in locs if any(k in (n + " " + u).lower() for k in keys)), None)
        if not url:
            print("no link found for", hall)
            continue
        page = BeautifulSoup(get(url), "html.parser")
        meal_urls = list(dict.fromkeys(u for _, u in anchors(page, url, "mealname")))
        print(hall, "meal pages:", len(meal_urls))
        for u in meal_urls:
            meal = meal_from_url(u)
            if not meal:
                continue
            before = len(items)
            html = scrape_meal(u, hall, meal, items, seen)
            print(" ", meal, len(items) - before, "items")
            if len(items) == before:
                dump(f"{hall.split()[0]}-{meal.replace(' ', '')}.html", html)
    if not items:
        print("No items parsed. Raw pages saved in debug/.")
        sys.exit(1)
    stamp = datetime.datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%b %d, %Y")
    pathlib.Path("menu.json").write_text(json.dumps({"updated": stamp, "items": items}))
    print(len(items), "items saved")

if __name__ == "__main__":
    main()
