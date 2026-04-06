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
            origin.push('main')
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
        logging.info("Starting Match Cycle (Schedules)...")
        api_matches = self.get_matches()
        
        for m in api_matches:
            team_a = m['teams']['home']['name']
            team_b = m['teams']['away']['name']
            match_date = m['fixture']['date'][:10]
            from slugify import slugify
            slug = slugify(f"{team_a}-vs-{team_b}-{match_date}")
            is_live = m['fixture']['status']['short'] in ['1H', '2H', 'HT']
            
            match_data = {
                "team_a": team_a,
                "team_b": team_b,
                "team_a_logo": m['teams']['home']['logo'],
                "team_b_logo": m['teams']['away']['logo'],
                "league": m['league']['name'],
                "time": m['fixture']['date'][11:16],
                "date": match_date,
                "channel": "بانتظار المصدر",
                "commentator": "قيد التحديد",
                "servers": [],
                "live": is_live,
                "slug": slug
            }
            match_data = self.enrich_match_metadata(match_data)
            # Initial generation without servers if not already scraped
            if f"/match/{slug}/" not in self.generator.scraped_urls:
                self.generator.generate_match_page(match_data)
        
        self.generator.generate_index()
        self.generator.generate_live_json()
        self.git_push()

    async def monitor_live_matches(self):
        """Scrapes and updates servers for active matches ONLY."""
        logging.info("Live Monitor: Checking active matches for streams...")
        api_matches = self.get_matches()
        live_matches = [m for m in api_matches if m['fixture']['status']['short'] in ['1H', '2H', 'HT', 'NS']] # NS = Not Started (check slightly before)
        
        count = 0
        for m in live_matches:
            team_a = m['teams']['home']['name']
            team_b = m['teams']['away']['name']
            
            # Scrape servers
            streams = await self.scraper.scrape_match_stream(f"{team_a} vs {team_b}")
            if streams:
                match_date = m['fixture']['date'][:10]
                from slugify import slugify
                slug = slugify(f"{team_a}-vs-{team_b}-{match_date}")
                
                match_data = {
                    "team_a": team_a,
                    "team_b": team_b,
                    "team_a_logo": m['teams']['home']['logo'],
                    "team_b_logo": m['teams']['away']['logo'],
                    "league": m['league']['name'],
                    "time": m['fixture']['date'][11:16],
                    "date": match_date,
                    "servers": streams,
                    "live": True,
                    "slug": slug
                }
                match_data = self.enrich_match_metadata(match_data)
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
            commentators = ["فارس عوض", "خليل البلوشي", "عصام الشوالي", "حفيظ دراجي", "عامر الخوذيري"]
            # Use a stable hash of the teams to keep the commentator consistent across runs
            idx = sum(ord(c) for c in (match_data['team_a'] + match_data['team_b'])) % len(commentators)
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
