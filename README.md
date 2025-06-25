# Trakt-to-Notion Sync

A Python script that syncs your [Trakt.tv](https://trakt.tv) watchlist to a [Notion](https://notion.so) database.

## 🔧 Features

- Syncs **movies**, **shows**, and **seasons** from Trakt watchlist
- Automatically removes items beyond the 100-item Trakt watchlist limit (FIFO)
- Adds removed items to Notion with:
  - Title, Media Type, Year
  - Trakt & IMDb links
  - Poster, Duration, Genre
  - IMDb Rating + Votes
  - Status: `Not on Trakt`
  - Date Removed
- Fully supports **DRY_RUN mode** for testing
- Optimized for cron job execution (headless/server environments)

## 📦 Requirements

- Python 3.8+
- Notion integration token
- Trakt API key + OAuth token
- TMDb API key
- OMDb API key (for IMDb ratings)

## �� File Structure
trakt_sync/
│
├── trakt_to_notion_sync.py # Main script
└── venv/ # Python virtual environment



## 🚀 Usage

```bash
# Clone the repo
git clone https://github.com/bequbed/trakt-to-notion-sync.git
cd trakt-to-notion-sync

# Set up virtualenv if needed
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt  # if you create one

# Run the script
python trakt_to_notion_sync.py

