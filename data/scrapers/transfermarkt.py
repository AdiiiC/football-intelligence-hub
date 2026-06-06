"""
Transfermarkt scraper — squad, market values, transfer news.
Uses cloudscraper to handle Cloudflare protection.
"""

import time
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import cloudscraper
from bs4 import BeautifulSoup

from config.settings import SCRAPER_HEADERS, CACHE_DIR, CACHE_TTL_SQUAD, CACHE_TTL_TRANSFERS

BASE_URL = "https://www.transfermarkt.com"

scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "mobile": False}
)
scraper.headers.update(SCRAPER_HEADERS)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _cache_path(key: str) -> Path:
    p = Path(CACHE_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{key}.json"


def _load_cache(key: str, ttl: int) -> Optional[dict]:
    cp = _cache_path(key)
    if not cp.exists():
        return None
    age = time.time() - cp.stat().st_mtime
    if age > ttl:
        return None
    with open(cp) as f:
        return json.load(f)


def _save_cache(key: str, data) -> None:
    with open(_cache_path(key), "w") as f:
        json.dump(data, f)


def _get(url: str, retries: int = 3) -> Optional[BeautifulSoup]:
    for attempt in range(retries):
        try:
            resp = scraper.get(url, timeout=15)
            if resp.status_code == 200:
                return BeautifulSoup(resp.text, "html.parser")
            time.sleep(2 ** attempt)
        except Exception:
            time.sleep(2 ** attempt)
    return None


def _valid_photo(url: str) -> str:
    """Return url if it's a real photo (>4KB), else empty string."""
    if not url or url.startswith("data:"):
        return ""
    try:
        r = scraper.get(url, timeout=8, stream=True)
        length = int(r.headers.get("Content-Length", 0))
        if length == 0:
            content = r.content
            length = len(content)
        return url if length > 4000 else ""
    except Exception:
        return ""


def _parse_value(raw: str) -> float:
    """Convert '€45m', '€500k', '€1.2bn' strings to float (in millions)."""
    raw = raw.strip().replace(",", ".")
    if not raw or raw in ("-", "—"):
        return 0.0
    m = re.search(r"[\d.]+", raw)
    if not m:
        return 0.0
    val = float(m.group())
    if "bn" in raw.lower():
        val *= 1000
    elif "k" in raw.lower():
        val /= 1000
    return round(val, 2)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_squad(club_slug: str, club_id: str) -> list[dict]:
    """
    Fetch full squad for a club from Transfermarkt.
    Returns list of player dicts.
    """
    cache_key = f"squad_{club_id}"
    cached = _load_cache(cache_key, CACHE_TTL_SQUAD)
    if cached:
        return cached

    # Use current season — determine dynamically (Jun+ = new season started)
    from datetime import datetime
    _now = datetime.now()
    _season = _now.year if _now.month >= 7 else _now.year - 1
    url = f"{BASE_URL}/{club_slug}/kader/verein/{club_id}/saison_id/{_season}"
    soup = _get(url)
    if not soup:
        return []

    players = []
    table = soup.find("table", {"class": "items"})
    if not table:
        return []

    rows = table.find_all("tr", {"class": ["odd", "even"]})
    for row in rows:
        try:
            # ── Name & profile link ───────────────────────────────────────
            # TM no longer adds spielprofil_tooltip class; link is inside
            # <td class="hauptlink"> inside the posrela inline-table
            posrela = row.find("td", {"class": "posrela"})
            if not posrela:
                continue
            name_link = posrela.find("td", {"class": "hauptlink"})
            if not name_link:
                # fallback: first <a> in posrela
                name_link_a = posrela.find("a")
            else:
                name_link_a = name_link.find("a")
            if not name_link_a:
                continue
            name = name_link_a.get_text(strip=True)
            if not name:
                continue
            profile_href = name_link_a.get("href", "")
            pid_m = re.search(r"/spieler/(\d+)", profile_href)
            player_id = pid_m.group(1) if pid_m else ""

            # ── Position ──────────────────────────────────────────────────
            # Second <td> (no rowspan) inside the inline-table
            position = ""
            inline_tbl = posrela.find("table", {"class": "inline-table"})
            if inline_tbl:
                tds = inline_tbl.find_all("td")
                for td in tds:
                    if not td.get("rowspan"):
                        txt = td.get_text(strip=True)
                        if txt and not td.find("a") and not td.find("img"):
                            position = txt
                            break

            # ── Jersey number ─────────────────────────────────────────────
            rn = row.find("div", {"class": "rn_nummer"})
            jersey_number = rn.get_text(strip=True) if rn else ""

            # ── Nationality (flag image title) ────────────────────────────
            nat_imgs = row.find_all("img", {"class": "flaggenrahmen"})
            nationality = nat_imgs[0].get("title", "") if nat_imgs else ""

            # ── Age, joined year, contract expiry (plain zentriert tds) ──────
            from datetime import datetime as _dt
            _curr_yr = _dt.now().year
            age = ""
            joined_year = None
            contract_year = None
            for td in row.find_all("td", {"class": "zentriert"}):
                if td.find("img") or td.find("a") or td.find("div"):
                    continue
                txt = td.get_text(strip=True)
                if re.match(r"^\d{2}$", txt):
                    age = txt
                else:
                    years_found = re.findall(r"\b((?:19|20)\d{2})\b", txt)
                    if years_found:
                        yr = int(years_found[-1])
                        if yr <= _curr_yr and joined_year is None:
                            joined_year = yr
                        elif yr > _curr_yr and contract_year is None:
                            contract_year = yr

            # ── Market value ──────────────────────────────────────────────
            mv_td = row.find("td", {"class": "rechts hauptlink"})
            if not mv_td:
                # fallback: last td that contains a euro sign
                for td in reversed(row.find_all("td")):
                    if "€" in td.get_text():
                        mv_td = td
                        break
            market_value = _parse_value(mv_td.get_text(strip=True)) if mv_td else 0.0

            # ── Photo (lazy-loaded data-src) ──────────────────────────────
            img_tag = posrela.find("img", {"class": "bilderrahmen-fixed"})
            if not img_tag:
                img_tag = posrela.find("img")
            photo_url = ""
            if img_tag:
                photo_url = img_tag.get("data-src") or img_tag.get("src", "")

            players.append({
                "id": player_id,
                "name": name,
                "position": position,
                "nationality": nationality,
                "age": age,
                "market_value_m": market_value,
                "joined_year": joined_year,
                "contract_expiry": str(contract_year) if contract_year else "",
                "photo_url": photo_url,
                "jersey_number": jersey_number,
                "profile_url": f"{BASE_URL}{profile_href}",
            })
        except Exception:
            continue

    _save_cache(cache_key, players)
    return players


def get_player_market_value_history(player_id: str) -> list[dict]:
    """
    Fetch market value history for a single player.
    Returns list of {date, value_m} dicts.
    """
    cache_key = f"mv_history_{player_id}"
    cached = _load_cache(cache_key, CACHE_TTL_SQUAD)
    if cached:
        return cached

    url = f"{BASE_URL}/ceapi/marketValueDevelopment/graph/{player_id}"
    try:
        resp = scraper.get(url, timeout=10)
        if resp.status_code != 200:
            return []
        data = resp.json()
        history = []
        for entry in data.get("list", []):
            raw_val = entry.get("mw", "0")
            history.append({
                "date": entry.get("datum_mw", ""),
                "value_m": _parse_value(str(raw_val)),
                "age": entry.get("age", ""),
            })
        _save_cache(cache_key, history)
        return history
    except Exception:
        return []


def get_transfer_news(club_slug: str, club_id: str) -> dict:
    """
    Fetch confirmed transfers + rumours for a club.
    Covers: last summer window, winter window, current summer window.
    Returns {"confirmed": [...], "rumours": [...]}.
    """
    cache_key = f"transfers_{club_id}"
    cached = _load_cache(cache_key, CACHE_TTL_TRANSFERS)
    if cached:
        return cached

    from datetime import datetime as _dt
    _now = _dt.now()
    # Football season year: 2025 = season 2025/26
    _curr_season = _now.year if _now.month >= 7 else _now.year - 1
    _prev_season = _curr_season - 1

    result = {"confirmed": [], "rumours": []}

    # --- Confirmed transfers: 3 windows ---
    # Summer YYYY   = saison_id/YYYY  w_s=s   (e.g. Summer 2025 → saison_id/2025)
    # Winter YYYY+1 = saison_id/YYYY  w_s=w   (e.g. Winter 2026 → saison_id/2025)
    # Current summer = saison_id/YYYY+1 w_s=s  (e.g. Summer 2026 → saison_id/2026)
    _WINDOWS = [
        (f"saison_id/{_curr_season}/pos/0/detailpos/0/w_s/s",   f"Summer {_curr_season}"),
        (f"saison_id/{_curr_season}/pos/0/detailpos/0/w_s/w",   f"Winter {_curr_season + 1}"),
        (f"saison_id/{_curr_season + 1}/pos/0/detailpos/0/w_s/s", f"Summer {_curr_season + 1}"),
    ]

    _ARRIVAL_LABELS   = {"arrivals", "zugänge", "arrivals (loans)", "zugänge (leihe)"}
    _DEPARTURE_LABELS = {"departures", "abgänge", "departures (loans)", "abgänge (leihe)"}

    seen = set()  # deduplicate across windows by (name, direction, club)

    def _scrape_window(suffix, window_label):
        url = f"{BASE_URL}/{club_slug}/transfers/verein/{club_id}/{suffix}"
        soup = _get(url)
        if not soup:
            return
        for heading in soup.find_all(["h2", "h3"]):
            heading_text = heading.get_text(strip=True).lower()
            if heading_text in _ARRIVAL_LABELS:
                direction = "in"
            elif heading_text in _DEPARTURE_LABELS:
                direction = "out"
            else:
                continue
            box = heading.find_parent(class_="box")
            if not box:
                continue
            table = box.find("table", {"class": "items"})
            if not table:
                continue
            for row in table.find_all("tr", {"class": ["odd", "even"]}):
                try:
                    inline = row.find("table", {"class": "inline-table"})
                    if not inline:
                        continue
                    img_tag = inline.find("img")
                    photo_url = ""
                    if img_tag:
                        photo_url = img_tag.get("data-src") or img_tag.get("src", "")
                        if photo_url.startswith("data:"):
                            photo_url = img_tag.get("data-src", "")
                    name_tag = inline.find("a", href=re.compile(r"/profil/spieler/"))
                    name = name_tag.get_text(strip=True) if name_tag else ""
                    trs = inline.find_all("tr")
                    pos = trs[1].get_text(strip=True) if len(trs) > 1 else ""
                    club_links = row.find_all("a", href=re.compile(r"/startseite/verein/"))
                    club_name = ""
                    for cl in reversed(club_links):
                        t = cl.get("title", "").strip()
                        if t:
                            club_name = t
                            break
                    fee_tag = row.find("td", class_=re.compile(r"rechts"))
                    fee_raw = fee_tag.get_text(strip=True).lower() if fee_tag else ""
                    fee = _parse_value(fee_raw)
                    deal_type = "loan" if "loan" in fee_raw or "leihe" in fee_raw else "permanent"
                    if not name:
                        continue
                    key = (name.lower(), direction, club_name.lower())
                    if key in seen:
                        continue
                    seen.add(key)
                    result["confirmed"].append({
                        "name": name,
                        "photo_url": photo_url,
                        "direction": direction,
                        "position": pos,
                        "club": club_name,
                        "fee_m": fee,
                        "deal_type": deal_type,
                        "window": window_label,
                        "type": "confirmed",
                        "source": "transfermarkt.com",
                    })
                except Exception:
                    continue

    for suffix, label in _WINDOWS:
        _scrape_window(suffix, label)

    # --- Rumours ---
    rumour_url = f"{BASE_URL}/{club_slug}/geruechte/verein/{club_id}"
    soup2 = _get(rumour_url)
    if soup2:
        table = soup2.find("table", {"class": "items"})
        if table:
            for row in table.find_all("tr", {"class": ["odd", "even"]}):
                try:
                    inline = row.find("table", {"class": "inline-table"})
                    if not inline:
                        continue
                    # Player photo
                    img_tag = inline.find("img")
                    photo_url = img_tag.get("src", "") if img_tag else ""
                    if photo_url.startswith("data:"):
                        photo_url = img_tag.get("data-src", "") if img_tag else ""
                    # Player name
                    name_tag = inline.find("a", href=re.compile(r"/profil/spieler/"))
                    name = name_tag.get_text(strip=True) if name_tag else ""
                    # Position
                    trs = inline.find_all("tr")
                    pos = trs[1].get_text(strip=True) if len(trs) > 1 else ""
                    # Current club (wappen icon link)
                    from_link = row.find("a", href=re.compile(r"/geruechte/verein/"))
                    from_club = from_link.get("title", "") if from_link else ""
                    # Market value
                    mv_td = row.find("td", {"class": re.compile(r"rechts.*hauptlink|hauptlink.*rechts")})
                    mv = _parse_value(mv_td.get_text(strip=True)) if mv_td else 0.0
                    # Source link / date
                    source_link = row.find("a", href=re.compile(r"/thread/"))
                    source = source_link.get("title", "transfermarkt.com") if source_link else "transfermarkt.com"
                    date_text = source_link.get_text(strip=True) if source_link else ""
                    if not name:
                        continue
                    result["rumours"].append({
                        "name": name,
                        "photo_url": photo_url,
                        "position": pos,
                        "club": from_club,
                        "market_value_m": mv,
                        "source": source,
                        "date": date_text,
                        "type": "rumour",
                    })
                except Exception:
                    continue

    _save_cache(cache_key, result)
    return result


def search_player(query: str) -> list[dict]:
    """Quick player search on Transfermarkt. Returns top results."""
    url = f"{BASE_URL}/schnellsuche/ergebnis/schnellsuche?query={query.replace(' ', '+')}&Spieler_page=0"
    soup = _get(url)
    if not soup:
        return []
    results = []
    table = soup.find("table", {"class": "items"})
    if not table:
        return []
    for row in table.find_all("tr", {"class": ["odd", "even"]})[:10]:
        try:
            name_tag = row.find("a", {"class": "spielprofil_tooltip"})
            name = name_tag.get_text(strip=True) if name_tag else ""
            href = name_tag.get("href", "") if name_tag else ""
            pid = re.search(r"/(\d+)$", href)
            pid = pid.group(1) if pid else ""
            mv_tag = row.find("td", {"class": "rechts"})
            mv = _parse_value(mv_tag.get_text(strip=True)) if mv_tag else 0.0
            results.append({"id": pid, "name": name, "market_value_m": mv, "profile_url": f"{BASE_URL}{href}"})
        except Exception:
            continue
    return results
