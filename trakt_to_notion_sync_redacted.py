from dotenv import load_dotenv
import os

# Load environment variables from .env
load_dotenv(dotenv_path="/opt/trakt_sync/.env")

import requests
import json
from datetime import datetime
import pytz
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# === USER CONFIGURATION ===
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("DATABASE_ID")
TRAKT_API_KEY = os.getenv("TRAKT_API_KEY")
TRAKT_USERNAME = os.getenv("TRAKT_USERNAME")
TRAKT_ACCESS_TOKEN = os.getenv("TRAKT_ACCESS_TOKEN")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
OMDB_API_KEY = os.getenv("OMDB_API_KEY")
DRY_RUN = os.getenv("DRY_RUN", "False").lower() == "true"
TRAKT_LIMIT = int(os.getenv("TRAKT_LIMIT", "100"))

# === HEADERS ===
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

TRAKT_HEADERS = {
    "Content-Type": "application/json",
    "trakt-api-version": "2",
    "trakt-api-key": TRAKT_API_KEY,
    "Authorization": f"Bearer {TRAKT_ACCESS_TOKEN}"
}

# === SESSION SETUP ===
def requests_session_with_retries():
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=1.5, status_forcelist=[500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session

session = requests_session_with_retries()

# === FETCH WATCHLIST ===
def get_trakt_watchlist_sorted():
    url = f"https://api.trakt.tv/users/{TRAKT_USERNAME}/watchlist"
    res = session.get(url, headers=TRAKT_HEADERS)
    if res.status_code != 200:
        print(f"❌ Failed to fetch Trakt watchlist: {res.status_code}")
        return []
    watchlist = res.json()
    return sorted(watchlist, key=lambda x: x.get("listed_at", ""))

# === TMDB + OMDB METADATA ===
def get_tmdb_details(tmdb_id, media_type):
    url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}?api_key={TMDB_API_KEY}"
    res = session.get(url)
    if res.status_code != 200:
        return {}
    data = res.json()
    runtime = data.get("runtime") or (data.get("episode_run_time") or [None])[0]
    return {
        "genres": [g["name"] for g in data.get("genres", [])],
        "runtime": runtime,
        "imdb": data.get("imdb_id"),
        "poster": f"https://image.tmdb.org/t/p/w500{data['poster_path']}" if data.get("poster_path") else None
    }

def get_imdb_rating(imdb_id):
    if not imdb_id:
        return None, None
    url = f"http://www.omdbapi.com/?apikey={OMDB_API_KEY}&i={imdb_id}"
    res = session.get(url)
    if res.status_code != 200:
        return None, None
    data = res.json()
    try:
        rating = float(data.get("imdbRating")) if data.get("imdbRating") != "N/A" else None
        votes = int(data.get("imdbVotes").replace(",", "")) if data.get("imdbVotes") != "N/A" else None
        return rating, votes
    except:
        return None, None

# === NOTION WRITER ===
def add_to_notion_as_not_on_trakt(item):
    media_type = item["type"]
    obj = item.get(media_type, {})
    ids = obj.get("ids", {})
    title = obj.get("title", "Untitled")
    year = obj.get("year", "")
    slug = ids.get("slug")
    trakt_url = f"https://trakt.tv/{media_type + 's'}/{slug}"

    tmdb_id = ids.get("tmdb")
    tmdb_type = "tv" if media_type == "show" else "movie"
    tmdb_data = get_tmdb_details(tmdb_id, tmdb_type)
    imdb_rating, imdb_votes = get_imdb_rating(tmdb_data.get("imdb"))

    now = datetime.now(pytz.timezone("Pacific/Auckland")).isoformat()
    notion_payload = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "Title": {"title": [{"text": {"content": f"{title} ({year})"}}]},
            "Media Type": {"select": {"name": media_type.capitalize()}},
            "Status": {"select": {"name": "Not on Trakt"}},
            "Trakt ID": {"url": trakt_url},
            "Trakt Watchlist": {"checkbox": False},
            "Date Removed": {"date": {"start": now}},
            "Source": {"multi_select": [{"name": "Trakt"}]},
            "IMDb": {"url": f"https://www.imdb.com/title/{tmdb_data.get('imdb')}"} if tmdb_data.get("imdb") else None,
            "Genres": {"multi_select": [{"name": g} for g in tmdb_data.get("genres", [])]} if tmdb_data.get("genres") else None,
            "Duration": {"rich_text": [{"text": {"content": f"{tmdb_data.get('runtime')} min"}}]} if tmdb_data.get("runtime") else None,
            "Poster": {"url": tmdb_data.get("poster")} if tmdb_data.get("poster") else None,
            "IMDb Rating": {"number": imdb_rating} if imdb_rating else None,
            "IMDb Votes": {"number": imdb_votes} if imdb_votes else None,
        }
    }

    notion_payload["properties"] = {k: v for k, v in notion_payload["properties"].items() if v is not None}

    if DRY_RUN:
        print(f"🧪 [DRY RUN] Would add to Notion: {title}")
    else:
        res = session.post("https://api.notion.com/v1/pages", headers=NOTION_HEADERS, data=json.dumps(notion_payload))
        if res.status_code != 200:
            print(f"❌ Failed to add {title}: {res.text}")
        else:
            print(f"✅ Added to Notion: {title}")

# === FIFO LIMIT + REMOVE ===
def trim_trakt_watchlist(watchlist):
    if len(watchlist) <= TRAKT_LIMIT:
        print("✅ Trakt watchlist is within 100-item limit.")
        return [], watchlist
    overflow = watchlist[:-TRAKT_LIMIT]
    keep = watchlist[-TRAKT_LIMIT:]

    if DRY_RUN:
        print(f"🧪 [DRY RUN] Would remove {len(overflow)} items from Trakt.")
    else:
        print(f"🧹 Removing {len(overflow)} items from Trakt...")
        payload = {"movies": [], "shows": [], "seasons": []}
        for item in overflow:
            media_type = item["type"]
            ids = item.get(media_type, {}).get("ids", {})
            wrapped = {"ids": ids}
            if media_type == "movie":
                payload["movies"].append(wrapped)
            elif media_type == "show":
                payload["shows"].append(wrapped)
            elif media_type == "season":
                payload["seasons"].append(wrapped)
        url = "https://api.trakt.tv/sync/watchlist/remove"
        res = session.post(url, headers=TRAKT_HEADERS, json=payload)
        if res.status_code not in [200, 201]:
            print(f"❌ Failed to remove items: {res.status_code} – {res.text}")
        else:
            print(f"✅ Removed {len(overflow)} items from Trakt.")
    return overflow, keep

# === ENTRYPOINT ===
if __name__ == "__main__":
    print("📥 Fetching Trakt watchlist...")
    watchlist = get_trakt_watchlist_sorted()

    print("⚖️ Checking for overflow (FIFO > 100)...")
    overflow_items, kept_items = trim_trakt_watchlist(watchlist)

    print("🟥 Syncing overflow items to Notion...")
    for item in overflow_items:
        add_to_notion_as_not_on_trakt(item)

    print("✅ All done.")
