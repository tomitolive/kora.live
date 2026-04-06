import os

# --- Domain & Deployment ---
DOMAIN = "https://cuplive.online"
GITHUB_REPO = "https://github.com/tomitolive/kora.live.git"

# --- API Keys ---
API_FOOTBALL_KEY = "228d747ea8a8bfc69be6c8f786f6259b"
API_FOOTBALL_HOST = "v3.football.api-sports.io"
API_FOOTBALL_URL = f"https://{API_FOOTBALL_HOST}"

CLAUDE_API_KEY = "YOUR_CLAUDE_API_KEY" # USER: Replace with your actual key
CLAUDE_MODEL = "claude-3-5-sonnet-20241022"

# --- Sources ---
NEWS_SOURCE = "https://www.live-soccer.info"
STREAM_SOURCE = "https://kooorasport.live"
PREMIUM_SOURCE = "https://a10.sia-koora.live/premium-1/"
CHANNEL_BASE = "koora-plus.top"
CHANNEL_RANGE = range(1, 51)

# --- Design Tokens (White & Green) ---
COLORS = {
    "bg": "#FFFFFF",
    "surface": "#F5F5F5",
    "primary": "#0A5C2A",
    "hover": "#1a7a3a",
    "text_main": "#111111",
    "text_secondary": "#555555",
    "border": "#E0E0E0",
    "white": "#FFFFFF"
}

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
DOCS_DIR = os.path.join(os.path.dirname(BASE_DIR), "docs") # Outside cuplive/ for GitHub Pages
SCRAPED_URLS_FILE = os.path.join(BASE_DIR, "scraped_urls.json")
CHANNEL_MAP_FILE = os.path.join(BASE_DIR, "channel_map.json")

# --- Settings ---
MAX_NEWS = 10
MAX_PAGES_PER_RUN = 10
DELAY = 2
