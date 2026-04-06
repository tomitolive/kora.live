import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import asyncio
import logging
import threading
import time
import requests
import datetime
from git import Repo
from slugify import slugify
from config import (
    API_FOOTBALL_KEY, API_FOOTBALL_HOST, API_FOOTBALL_URL,
    BASE_DIR, DOCS_DIR, GITHUB_REPO, MAX_PAGES_PER_RUN
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
            origin.push('master')
            logging.info("Changes pushed to GitHub main branch.")
        except Exception as e:
            logging.error(f"Git Push Error: {e}")

    def cleanup(self):
        """Clears old content to start fresh as requested."""
        import shutil
        logging.info("Cleaning up old content...")
        for folder in ['match', 'news']:
            path = os.path.join(DOCS_DIR, folder)
            if os.path.exists(path):
                shutil.rmtree(path)
            os.makedirs(path, exist_ok=True)
        if os.path.exists(os.path.join(BASE_DIR, "scraped_urls.json")):
            os.remove(os.path.join(BASE_DIR, "scraped_urls.json"))
        self.generator.scraped_urls = {}

    def get_matches(self):
        import datetime
        today = datetime.date.today()
        dates = [
            (today - datetime.timedelta(days=1)).strftime("%Y-%m-%d"),
            today.strftime("%Y-%m-%d"),
            (today + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        ]
        all_matches = []
        headers = {'x-rapidapi-key': API_FOOTBALL_KEY, 'x-rapidapi-host': API_FOOTBALL_HOST}
        
        for d in dates:
            url = f"{API_FOOTBALL_URL}/fixtures?date={d}"
            try:
                res = requests.get(url, headers=headers)
                all_matches.extend(res.json().get('response', []))
            except Exception as e:
                logging.error(f"Error fetching matches for {d}: {e}")
                
        return all_matches

    async def run_news_cycle(self):
        logging.info("Starting News Cycle (Target: 10 articles)...")
        headlines = await self.scraper.scrape_news_headlines()
        
        generated_count = 0
        from config import MAX_PAGES_PER_RUN
        
        for h in headlines:
            if generated_count >= 10: # Strictly 10 as requested
                break
                
            from slugify import slugify
            slug = slugify(h['title'])
            if f"/news/{slug}/" not in self.generator.scraped_urls:
                content = self.news_gen.generate_article(h['title'])
                article_data = {
                    "article_title": h['title'],
                    "date": time.strftime("%Y-%m-%d"),
                    # Use a dynamic sports related image from a collection
                    "image": f"https://images.unsplash.com/photo-1508098682722-e99c43a406b2?q=80&w=1000&sig={generated_count}", 
                    "content": content,
                    "related": []
                }
                self.generator.generate_article_page(article_data)
                generated_count += 1
        
        self.generator.generate_news_list()
        self.generator.generate_index()
        self.generator.generate_sitemap()
        self.generator.generate_live_json()
        self.git_push()

    async def run_match_cycle(self):
        """Generates static pages for all matches (yesterday/today/tomorrow)."""
        logging.info("Starting Match Cycle (Live-Soccer Scraping)...")
        
        for day in ['yesterday', 'today', 'tomorrow']:
            matches = await self.scraper.scrape_live_soccer_matches(day)
            import datetime
            if day == 'yesterday':
                target_date = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
            elif day == 'today':
                target_date = datetime.date.today().strftime("%Y-%m-%d")
            else:
                target_date = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

            for m in matches:
                from slugify import slugify
                slug = slugify(f"{m['team_a']}-vs-{m['team_b']}-{target_date}")
                
                # Check if it was already scraped and has servers
                existing_servers = []
                try:
                    import json, os
                    from config import DOCS_DIR
                    json_path = os.path.join(DOCS_DIR, "match", slug, "data.json")
                    if os.path.exists(json_path):
                        with open(json_path, 'r', encoding='utf-8') as f:
                            old_data = json.load(f)
                            existing_servers = old_data.get('servers', [])
                except:
                    pass
                
                match_data = {
                    "team_a": m['team_a'],
                    "team_b": m['team_b'],
                    "team_a_logo": m['team_a_logo'],
                    "team_b_logo": m['team_b_logo'],
                    "league": m['league'],
                    "time": m['time'],
                    "date": target_date,
                    "channel": m['channel'],
                    "commentator": m['commentator'],
                    "stream_url": m.get('stream_url'),
                    "servers": existing_servers,
                    "live": m['live'],
                    "slug": slug
                }
                # Initial generation, preserving existing servers
                self.generator.generate_match_page(match_data)
        
        self.generator.generate_index()
        self.generator.generate_live_json()
        self.git_push()

    async def monitor_live_matches(self):
        """Scrapes and updates servers for active matches ONLY."""
        logging.info("Live Monitor: Checking active matches for streams...")
        live_matches = await self.scraper.scrape_live_soccer_matches('today')
        live_matches = [m for m in live_matches if m['live']]
        
        count = 0
        import datetime
        today = datetime.date.today().strftime("%Y-%m-%d")
        
        for m in live_matches:
            # Scrape servers using the direct stream_url found on the card
            streams = await self.scraper.scrape_match_stream(f"{m['team_a']} vs {m['team_b']}", m.get('stream_url'))
            if streams:
                from slugify import slugify
                slug = slugify(f"{m['team_a']}-vs-{m['team_b']}-{today}")
                
                match_data = m.copy()
                match_data.update({
                    "servers": streams,
                    "date": today,
                    "slug": slug
                })
                # Update both the HTML and the dedicated JSON
                self.generator.generate_match_page(match_data)
                self.generator.generate_match_json(match_data)
                count += 1
        
        if count > 0:
            self.generator.generate_index()
            self.generator.generate_live_json()
            self.git_push()

    def live_monitor_thread(self):
        """Thread to monitor live matches specifically and frequently (every 2.5 minutes)."""
        while True:
            logging.info("Live Monitor Thread: Checking active matches...")
            try:
                asyncio.run(self.monitor_live_matches())
            except Exception as e:
                logging.error(f"Live Monitor Error: {e}")
            time.sleep(150)

    def enrich_match_metadata(self, match_data):
        """Enriches match data with premium placeholders if metadata is missing."""
        if not match_data.get('channel') or match_data['channel'] == "بانتظار المصدر":
            if "Premier League" in match_data['league']:
                match_data['channel'] = "beIN Sports 1 HD"
            elif "La Liga" in match_data['league'] or "الدوري الإسباني" in match_data['league']:
                match_data['channel'] = "beIN Sports 3 HD"
            else:
                match_data['channel'] = "قناة رياضية HD"
        
        if not match_data.get('commentator') or match_data['commentator'] == "قيد التحديد":
            commentators = ["فارس عوض", "خليل البلوشي", "عصام الشوالي", "حفيظ دراجي", "عامر الخوذيري", "خليل البلوشي"]
            # Use a stable hash of the teams to keep the commentator consistent across runs
            combined = (match_data['team_a'] + match_data['team_b']).encode('utf-8')
            import hashlib
            idx = int(hashlib.md5(combined).hexdigest(), 16) % len(commentators)
            match_data['commentator'] = commentators[idx]
        
        return match_data

    async def start(self):
        # 1. Fresh Start
        self.cleanup()
        
        # 2. Daily Setup (News + Schedules)
        await self.run_match_cycle()
        await self.run_news_cycle()
        
        # 3. Start Live Monitor Thread
        threading.Thread(target=self.live_monitor_thread, daemon=True).start()
        
        # 4. Main Daily Cycle (Repeats every 12h for updates)
        while True:
            logging.info("Main Cycle: Updating schedules and news...")
            # await self.scraper.brute_force_channels() # Skip for now to speed up test
            await self.run_match_cycle()
            await self.run_news_cycle()
            
            logging.info("Main Cycle: Sleeping for 12h.")
            await asyncio.sleep(12 * 3600)

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    bot = CupLiveBot()
    asyncio.run(bot.start())
