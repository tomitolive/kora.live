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
        from config import PREMIUM_SOURCE, STREAM_SOURCE
        logging.info(f"Searching stream for {match_name}...")
        
        # Try Premium Source first as requested by user
        sources = await self.scrape_from_url(PREMIUM_SOURCE, match_name)
        if sources:
            return sources
            
        # Fallback to secondary source
        return await self.scrape_from_url(STREAM_SOURCE, match_name)

    async def scrape_from_url(self, base_url, match_name=None):
        logging.info(f"Scraping from: {base_url}")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(base_url, wait_until="networkidle", timeout=60000)
                
                target_url = base_url
                if match_name:
                    # Look for match link if not already on a specific match page
                    links = await page.query_selector_all("a")
                    for link in links:
                        text = await link.inner_text()
                        if any(word.lower() in text.lower() for word in match_name.split() if len(word) > 3):
                            found_href = await link.get_attribute("href")
                            if found_href:
                                from urllib.parse import urljoin
                                target_url = urljoin(base_url, found_href)
                                break
                
                if target_url != base_url:
                    await page.goto(target_url, wait_until="networkidle", timeout=60000)
                
                sources = []
                from urllib.parse import urljoin
                
                for frame in page.frames:
                    try:
                        # Improved aplr-menu selector
                        menu_links = await frame.query_selector_all(".aplr-menu a, ul.aplr-menu li a, .aplr-link")
                        for link in menu_links:
                            href = await link.get_attribute("href")
                            text = await link.inner_text()
                            if href and href != "#":
                                full_url = urljoin(frame.url, href)
                                if not any(s['url'] == full_url for s in sources):
                                    sources.append({
                                        "name": text.strip() or f"سيرفر {len(sources)+1}", 
                                        "url": full_url
                                    })
                    except:
                        continue
                
                # If still no sources, look for iframes
                if not sources:
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
                logging.error(f"Error scraping {base_url}: {e}")
            finally:
                await browser.close()
        return []

    async def scrape_live_soccer_matches(self, date_tab='today'):
        """Scrapes matches for yesterday, today, or tomorrow from live-soccer.info."""
        url_map = {
            'yesterday': "https://www.live-soccer.info/matches-yesterday/",
            'today': "https://www.live-soccer.info/",
            'tomorrow': "https://www.live-soccer.info/matches-tomorrow/"
        }
        url = url_map.get(date_tab, url_map['today'])
        logging.info(f"Scraping matches from {url}...")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(url, wait_until="networkidle", timeout=60000)
                matches = []
                # Select all match cards
                cards = await page.query_selector_all(".AY_Match")
                
                for card in cards:
                    try:
                        # Teams & Logos
                        tm1_name = await (await card.query_selector(".TM1 .TM_Name")).inner_text()
                        tm1_logo = await (await card.query_selector(".TM1 .TM_Logo img")).get_attribute("data-src")
                        tm2_name = await (await card.query_selector(".TM2 .TM_Name")).inner_text()
                        tm2_logo = await (await card.query_selector(".TM2 .TM_Logo img")).get_attribute("data-src")
                        
                        # Match Info (Channel, Commentator, League)
                        info_items = await card.query_selector_all(".MT_Info ul li span")
                        channel = await info_items[0].inner_text() if len(info_items) > 0 else "TBD"
                        commentator = await info_items[1].inner_text() if len(info_items) > 1 else "TBD"
                        league = await info_items[2].inner_text() if len(info_items) > 2 else "TBD"
                        
                        # Time / Status
                        status_el = await card.query_selector(".MT_Status")
                        time_text = await status_el.inner_text() if status_el else "00:00"
                        
                        # Stream Link
                        stream_link_el = await card.query_selector("a")
                        stream_url = await stream_link_el.get_attribute("href") if stream_link_el else None
                        if stream_url and not stream_url.startswith("http"):
                            from urllib.parse import urljoin
                            stream_url = urljoin(url, stream_url)
                        
                        is_live = "live" in (await card.get_attribute("class"))
                        
                        matches.append({
                            "team_a": tm1_name.strip(),
                            "team_b": tm2_name.strip(),
                            "team_a_logo": tm1_logo,
                            "team_b_logo": tm2_logo,
                            "league": league.strip(),
                            "time": time_text.strip(),
                            "channel": channel.strip(),
                            "commentator": commentator.strip(),
                            "stream_url": stream_url,
                            "live": is_live
                        })
                    except Exception as e:
                        logging.error(f"Error parsing match card: {e}")
                        continue
                return matches
            except Exception as e:
                logging.error(f"Error scraping matches from {url}: {e}")
                return []
            finally:
                await browser.close()

    async def scrape_match_stream(self, match_name, stream_url=None):
        from config import PREMIUM_SOURCE, STREAM_SOURCE
        logging.info(f"Searching stream for {match_name}...")
        
        # 1. If we have a direct stream_url from the match card, try it first
        if stream_url:
            sources = await self.scrape_from_url(stream_url)
            if sources: return sources
            
        # 2. Try Premium Source provided by user
        sources = await self.scrape_from_url(PREMIUM_SOURCE, match_name)
        if sources: return sources
            
        # 3. Fallback to secondary source
        return await self.scrape_from_url(STREAM_SOURCE, match_name)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scraper = CupLiveScraper()
    # asyncio.run(scraper.scrape_news_headlines())
