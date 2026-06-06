# ⚽ Football Intelligence Hub

A **Streamlit-powered football analytics platform** covering the top 5 European leagues — Premier League, La Liga, Bundesliga, Serie A, and Ligue 1. Built for data-driven transfer analysis, squad evaluation, and real-time transfer tracking.

---

## 🖥️ Live Features

### 📋 Squad Overview
- Full squad roster with **EA FC 26 player cards** (real portraits, PAC/SHO/PAS/DRI/DEF/PHY attributes)
- **Sell candidate analysis** with tenure-aware signals:
  - Contract expiry (≤1yr / ≤2yr)
  - Stat peer comparison vs. **top-6 league peers** (for players with ≥2 years at the club)
  - **UCL performance comparison** (FBref Champions League stats)
  - **Multi-season year-on-year xG decline** (2023→2024→2025)
  - **Team playstyle compatibility** (EA PlayStyles × squad archetype)
  - Peak value window (age ≥28 + MV ≥€30M)
  - Positional squad surplus
- **Squad weakness detection** by position group
- Team playstyle archetype determined from EA PlayStyle tags across the squad

### 🎯 Transfer Targets
- AI-powered buy recommendations based on squad weaknesses
- **Full candidate pool** from Understat 2025 enriched with EA FC ratings
- EA portrait cards for all candidates with market value estimation
- Budget and age filters

### 📊 Player Profile
- **Large hero card** — portrait, overall, PAC/SHO/PAS/DRI/DEF/PHY, sub-attributes, play style badges
- **Radar chart** vs. position-group league averages (FBref)
- **Shot map** — pitch heatmap of shots with xG value
- **xG timeline** — rolling xG over the season
- **Market value history** chart (Transfermarkt)
- **Transfer fee prediction** with price range gauge
- **Club fit analysis** — playstyle and stat compatibility score

### 📰 Transfer News
- **Confirmed transfers** from last 3 windows: Summer 2025, Winter 2026, Summer 2026
- Window badges (☀ Summer / ❄ Winter), deal type (⇄ Permanent / ↺ Loan), direction (IN/OUT)
- Transfer rumours feed
- **Live Ticker** strip with scrolling confirmed headlines
- **🔄 Refresh** button to bust cache and fetch the latest signings
- League Feed mode — aggregate top-10 clubs in one view

---

## 🗂️ Project Structure

```
Football/
├── app.py                        # Streamlit entry point
├── requirements.txt
├── config/
│   ├── settings.py               # League configs, cache TTLs, position groups
│   └── leagues.json              # Club slugs, TM IDs, EA team IDs
├── data/
│   ├── fetchers/
│   │   └── squad.py              # Aggregates TM + EA + Understat into player objects
│   └── scrapers/
│       ├── transfermarkt.py      # Squad, transfers (confirmed + rumours), player search
│       ├── ea_ratings.py         # EA FC 26 ratings, portraits, PlayStyles
│       ├── understat.py          # xG / xA / shots (POST API, 2023–2025 seasons)
│       └── fbref.py              # FBref domestic stats + UCL (comp ID 8)
├── models/
│   ├── squad_analyzer.py         # Sell/buy logic, playstyle detection, peer comparison
│   └── price_predictor.py        # Transfer fee prediction model
├── pages/
│   ├── 01_Squad_Overview.py      # Squad cards, sell analysis, weakness report
│   ├── 02_Transfer_Targets.py    # Buy targets with candidate pool
│   ├── 03_Player_Profile.py      # Hero card, radar, shot map, xG, value, fit
│   └── 04_Transfer_News.py       # Confirmed transfers + rumours feed
└── ui/
    ├── components/
    │   ├── fifa_card.py          # EA FC-style HTML card renderer
    │   ├── transfer_feed.py      # Transfer card + ticker components
    │   ├── stat_charts.py        # Radar, shot map, xG timeline, value chart
    │   └── formation.py          # Formation visualiser
    └── styles/
        └── theme.css             # Dark theme CSS
```

---

## 🔌 Data Sources

| Source | What it provides | Method |
|---|---|---|
| **Transfermarkt** | Squad rosters, market values, confirmed transfers, rumours | `cloudscraper` HTML parsing |
| **EA FC 26** | Player overall, PAC/SHO/PAS/DRI/DEF/PHY, sub-attrs, PlayStyles, portraits | `__NEXT_DATA__` JSON from EA ratings page |
| **Understat** | xG, xA, npxG, shots, key passes per 90 (2023–2025) | POST API `/main/getPlayersStats/` |
| **FBref** | Domestic league + UCL (comp 8) per-90 stats, percentiles | HTML table scraping |

---

## 🧠 Key Intelligence Logic

### Sell Candidate Scoring
Players are scored across these signals — **card rating is never a sell signal**:

| Signal | Score | Condition |
|---|---|---|
| Contract expiring ≤1yr | +4 | Dynamic year check |
| Contract expiring ≤2yr | +2 | Dynamic year check |
| Below 25th pct vs peers | +3 | Top-6 peers if t≥2yrs, else full league |
| UCL underperformer | +3 | FBref UCL stats below 25th pct |
| UCL elite performer | −2 | FBref UCL stats above 75th pct (keep signal) |
| YoY xG decline >25% | +2 | Each confirmed season |
| Sustained 2-yr decline | +4 | Both seasons declining |
| Peak value window | +2 | Age ≥28 and MV ≥€30M |
| Squad surplus | +1 | Above ideal depth, not highest MV at position |
| Playstyle mismatch | +2 | EA PlayStyles vs team archetype |
| Style pillar | −1 | Strong fit for dominant team system |

### Team Playstyle Detection
Squad EA PlayStyles are tallied across 5 archetypes:
- **Possession/Technical** — Incisive Pass, Technical, Tiki Taka
- **High Press/Gegenpressing** — Press Proven, Relentless, Intercept
- **Counter-Attack/Direct** — Rapid, Long Ball Pass, First Touch
- **Physical/Aerial** — Aerial+, Power Header, Bruiser
- **Creative/Fluid** — Flair, Trickster, Trivela

### Transfer Window Coverage
Confirmed transfers are fetched for exactly 3 windows using TM's `saison_id` + `w_s` URL params:
- `Summer YYYY` — `saison_id/{season}&w_s=s`
- `Winter YYYY+1` — `saison_id/{season}&w_s=w`
- `Summer YYYY+1` — `saison_id/{season+1}&w_s=s`

---

## 🚀 Setup & Run

### 1. Clone
```bash
git clone https://github.com/AdiiiC/football-intelligence-hub.git
cd football-intelligence-hub
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Run
```bash
streamlit run app.py
```

The app runs at `http://localhost:8501`. Data is cached locally in `data/cache/` — first load per club takes ~10–30s; subsequent loads are instant.

---

## ⚙️ Configuration

Edit `config/settings.py` to adjust:
- `CACHE_TTL_SQUAD` — squad cache duration (default 24h)
- `CACHE_TTL_TRANSFERS` — transfer news cache (default 1h)
- `TOP_5_LEAGUES` — league names, flags, Understat IDs

---

## 📦 Dependencies

- **Streamlit** ≥1.35 — UI framework
- **cloudscraper** — Cloudflare-protected scraping (Transfermarkt)
- **BeautifulSoup4 + lxml** — HTML parsing
- **pandas / numpy** — data manipulation
- **plotly** — interactive charts
- **mplsoccer** — shot map pitch rendering
- **scikit-learn / xgboost** — transfer fee prediction model

---

## 🛣️ Planned Upgrades

See `next_upgrades.txt` for the full roadmap.

---

*Built with Python 3.9+ · Data from Transfermarkt, EA FC, Understat, FBref*
