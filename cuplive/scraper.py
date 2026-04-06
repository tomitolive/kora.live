import asyncio
import os
import json
import logging
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from config import (
    NEWS_SOURCE, STREAM_SOURCE, CHANNEL_BASE, CHANNEL_RANGE,
    CHANNEL_MAP_FILE, DELAY
)

class CupLiveScraper:
    def __init__(self):
        self.channel_map = self.load_channel_map()

    def load_channel_map(self):
        if os.path.exists(CHANNEL_MAP_FILE):
            try:
                with open(CHANNEL_MAP_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save_channel_map(self):
        with open(CHANNEL_MAP_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.channel_map, f, ensure_ascii=False, indent=4)

    async def scrape_news_headlines(self):
        logging.info(f"Scraping news headlines from {NEWS_SOURCE}...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                # Add a realistic User-Agent to avoid blocks
                await page.goto(NEWS_SOURCE, wait_until="networkidle", timeout=60000)
                content = await page.content()
                soup = BeautifulSoup(content, 'lxml')
                headlines = []
                # Adjust selector based on live-soccer.info
                for item in soup.select("h2.entry-title a, .post-title a")[:10]:
                    headlines.append({
                        "title": item.get_text().strip(),
                        "url": item.get("href")
                    })
                return headlines
            except Exception as e:
                logging.error(f"Error scraping news: {e}")
                return []
            finally:
                await browser.close()

    async def brute_force_channels(self):
        logging.info("Starting channel mapping (tv1-50)...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            for i in CHANNEL_RANGE:
                url = f"https://tv{i}.{CHANNEL_BASE}"
                try:
                    page = await context.new_page()
                    # Short timeout for brute force
                    await page.goto(url, timeout=12000, wait_until="domcontentloaded")
                    title = await page.title()
                    # Clean title: "البث المباشر لقناة بي ان سبورت 1" -> "بي ان سبورت 1"
                    name = title.replace("بث مباشر", "").replace("قناة", "").replace("|", "").replace("-", "").strip()
                    if name:
                        self.channel_map[f"tv{i}"] = {"name": name, "url": url}
                        logging.info(f"Mapped tv{i} -> {name}")
                    await page.close()
                except:
                    continue
            await browser.close()
        self.save_channel_map()

    async def scrape_match_stream(self, match_name):
        logging.info(f"Searching stream for {match_name} on {STREAM_SOURCE}...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(STREAM_SOURCE, wait_until="networkidle", timeout=60000)
                # Simple keyword search in links
                links = await page.query_selector_all("a")
                target_url = None
                for link in links:
                    text = await link.inner_text()
                    if any(word.lower() in text.lower() for word in match_name.split() if len(word) > 3):
                        target_url = await link.get_attribute("href")
                        break
                
                if target_url:
                    if not target_url.startswith("http"):
                        from urllib.parse import urljoin
                        target_url = urljoin(STREAM_SOURCE, target_url)
                    
                    await page.goto(target_url, wait_until="networkidle", timeout=60000)
                    
                    # 1. Look for aplr-menu links (Specific user requirement)
                    # Use a recursive check across all frames as menus are often in side-loaded players
                    sources = []
                    from urllib.parse import urljoin
                    
                    for frame in page.frames:
                        try:
                            # Support multiple selector variants for maximum coverage
                            menu_links = await frame.query_selector_all(".aplr-menu a.aplr-link, ul.aplr-menu li a")
                            for link in menu_links:
                                href = await link.get_attribute("href")
                                text = await link.inner_text()
                                if href and href != "#":
                                    full_url = urljoin(frame.url, href)
                                    # Avoid duplicates
                                    if not any(s['url'] == full_url for s in sources):
                                        sources.append({
                                            "name": text.strip() or f"سيرفر {len(sources)+1}", 
                                            "url": full_url
                                        })
                        except:
                            continue
                    
                    # 2. Fallback to iframes if no menu links found or alongside them
                    # Check all frames for iframes as well, but main page is usually enough
                    for frame in page.frames:
                        try:
                            iframes = await frame.query_selector_all("iframe[src]")
                            for ifr in iframes:
                                src = await ifr.get_attribute("src")
                                if src and "google" not in src and "ads" not in src and not src.startswith("data:"):
                                    full_src = urljoin(frame.url, src)
                                    if not any(s['url'] == full_src for s in sources):
                                        sources.append({"name": f"سيرفر {len(sources)+1}", "url": full_src})
                        except:
                            continue
                    
                    return sources
            except Exception as e:
                logging.error(f"Error scraping match stream: {e}")
            finally:
                await browser.close()
        return []

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scraper = CupLiveScraper()
    # asyncio.run(scraper.scrape_news_headlines())
