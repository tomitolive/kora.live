import asyncio
import os
import logging
import threading
import time
import requests
from git import Repo
from config import (
    API_FOOTBALL_KEY, API_FOOTBALL_HOST, API_FOOTBALL_URL,
    BASE_DIR, DOCS_DIR, GITHUB_REPO
)
from scraper import CupLiveScraper
from generator import SiteGenerator
from news_generator import NewsGenerator

class CupLiveBot:
    def __init__(self):
        self.scraper = CupLiveScraper()
        self.generator = SiteGenerator()
        self.news_gen = NewsGenerator()
        self.repo = self.init_repo()

    def init_repo(self):
        try:
            return Repo(os.path.dirname(BASE_DIR))
        except:
            return None

    def git_push(self):
        if not self.repo: return
        try:
            self.repo.git.add(A=True)
            self.repo.index.commit("Bot Update: Content sync")
            origin = self.repo.remote(name='origin')
            origin.push()
            logging.info("Changes pushed to GitHub.")
        except Exception as e:
            logging.error(f"Git Push Error: {e}")

    def get_matches(self):
        import datetime
        today = datetime.date.today().strftime("%Y-%m-%d")
        url = f"{API_FOOTBALL_URL}/fixtures?date={today}"
        headers = {'x-rapidapi-key': API_FOOTBALL_KEY, 'x-rapidapi-host': API_FOOTBALL_HOST}
        try:
            res = requests.get(url, headers=headers)
            return res.json().get('response', [])
        except:
            return []

    async def run_news_cycle(self):
        logging.info("Starting News Cycle...")
        headlines = await self.scraper.scrape_news_headlines()
        for h in headlines:
            from slugify import slugify
            slug = slugify(h['title'])
            if f"/news/{slug}/" not in self.generator.scraped_urls:
                content = self.news_gen.generate_article(h['title'])
                article_data = {
                    "article_title": h['title'],
                    "date": time.strftime("%Y-%m-%d"),
                    "image": "https://images.unsplash.com/photo-1508098682722-e99c43a406b2?q=80&w=1000", # Placeholder
                    "content": content,
                    "related": []
                }
                self.generator.generate_article_page(article_data)
        
        self.generator.generate_news_list()
        self.generator.generate_index()
        self.generator.generate_sitemap()
        self.git_push()

    async def run_match_cycle(self):
        logging.info("Starting Match Cycle...")
        api_matches = self.get_matches()
        for m in api_matches:
            match_data = {
                "team_a": m['teams']['home']['name'],
                "team_b": m['teams']['away']['name'],
                "league": m['league']['name'],
                "time": m['fixture']['date'][11:16],
                "date": m['fixture']['date'][:10],
                "channel": "بانتظار المصدر",
                "servers": [{"name": "سيرفر 1", "url": "https://tv1.koora-plus.top"}],
                "live": m['fixture']['status']['short'] in ['1H', '2H', 'HT']
            }
            # Try to scrape real stream link if live
            if match_data['live']:
                streams = await self.scraper.scrape_match_stream(f"{match_data['team_a']} vs {match_data['team_b']}")
                if streams: match_data['servers'] = streams
            
            self.generator.generate_match_page(match_data)
        
        self.generator.generate_index()
        self.git_push()

    def match_monitor_thread(self):
        """Thread to monitor live matches every 5 minutes"""
        while True:
            logging.info("Monitor Thread: Checking live matches...")
            asyncio.run(self.run_match_cycle())
            time.sleep(300)

    async def start(self):
        # Start monitor thread
        threading.Thread(target=self.match_monitor_thread, daemon=True).start()
        
        # Main Daily Cycle
        while True:
            logging.info("Main Cycle: Starting daily updates...")
            # 1. Update channel map
            await self.scraper.brute_force_channels()
            
            # 2. Run News cycle
            await self.run_news_cycle()
            
            # Wait 24 hours
            logging.info("Main Cycle: Sleeping for 24h.")
            await asyncio.sleep(24 * 3600)

if __name__ == "__main__":
    import os
    logging.basicConfig(level=logging.INFO)
    bot = CupLiveBot()
    asyncio.run(bot.start())
