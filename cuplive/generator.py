import os
import json
import logging
from jinja2 import Environment, FileSystemLoader
from slugify import slugify
from config import (
    TEMPLATES_DIR, DOCS_DIR, SCRAPED_URLS_FILE, COLORS
)

class SiteGenerator:
    def __init__(self):
        self.env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
        self.scraped_urls = self.load_scraped_urls()
        self.common_data = {
            "colors": COLORS
        }
        os.makedirs(DOCS_DIR, exist_ok=True)

    def load_scraped_urls(self):
        if os.path.exists(SCRAPED_URLS_FILE):
            try:
                with open(SCRAPED_URLS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save_scraped_urls(self):
        with open(SCRAPED_URLS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.scraped_urls, f, ensure_ascii=False, indent=4)

    def render_to_file(self, template_name, output_path, data):
        try:
            template = self.env.get_template(template_name)
            content = template.render({**self.common_data, **data})
            
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)
            logging.info(f"Rendered: {output_path}")
        except Exception as e:
            logging.error(f"Render error for {output_path}: {e}")

    def generate_match_page(self, match_data):
        slug = slugify(f"{match_data['team_a']}-vs-{match_data['team_b']}-{match_data['date']}")
        match_data['slug'] = slug
        match_dir = os.path.join(DOCS_DIR, "match", slug)
        os.makedirs(match_dir, exist_ok=True)
        
        # Render match index
        output_path = os.path.join(match_dir, "index.html")
        template = self.env.get_template("match.html")
        
        # Link to watch page if servers exist
        has_servers = bool(match_data.get('servers'))
        watch_url = f"/match/{match_data['slug']}/watch.html" if has_servers else None
        
        html = template.render(
            **match_data,
            watch_url=watch_url,
            colors=COLORS
        )
        with open(output_path, "w") as f:
            f.write(html)
            
        # 4. Generate watch.html if servers available
        if has_servers:
            self.generate_watch_page(match_data)
        
        self.scraped_urls[f"/match/{slug}/"] = {
            "type": "match",
            "slug": slug,
            "title": f"{match_data['team_a']} vs {match_data['team_b']}",
            "team_a": match_data['team_a'],
            "team_b": match_data['team_b'],
            "league": match_data['league'],
            "time": match_data['time'],
            "date": match_data['date'],
            "live": match_data.get('live', False),
            "watch_url": watch_url
        }
        self.save_scraped_urls()

    def generate_watch_page(self, match_data):
        match_dir = os.path.join(DOCS_DIR, "match", match_data['slug'])
        os.makedirs(match_dir, exist_ok=True)
        
        output_path = os.path.join(match_dir, "watch.html")
        template = self.env.get_template("watch.html")
        
        # Use extracted servers
        servers = match_data.get('servers', [])
        
        html = template.render(
            **match_data,
            servers=servers,
            colors=COLORS
        )
        with open(output_path, "w") as f:
            f.write(html)
        logging.info(f"Generated watch page: {output_path}")

    def generate_article_page(self, article_data):
        slug = slugify(article_data['article_title'])
        output_dir = os.path.join(DOCS_DIR, "news", slug)
        output_file = os.path.join(output_dir, "index.html")
        
        self.render_to_file("article.html", output_file, article_data)
        
        self.scraped_urls[f"/news/{slug}/"] = {
            "type": "news",
            "slug": slug,
            "title": article_data['article_title'],
            "excerpt": article_data.get('excerpt', article_data['article_title'][:150] + "..."),
            "image": article_data.get('image'),
            "date": article_data['date']
        }
        self.save_scraped_urls()

    def generate_index(self):
        # Get latest matches and news from scraped_urls
        all_items = list(self.scraped_urls.values())
        matches = [v for v in all_items if v.get('type') == 'match']
        latest_matches = matches[-6:] if len(matches) >= 6 else matches
        
        news = [v for v in all_items if v.get('type') == 'news']
        latest_news = news[-6:] if len(news) >= 6 else news
        
        data = {
            "matches": latest_matches,
            "news": latest_news
        }
        self.render_to_file("index.html", os.path.join(DOCS_DIR, "index.html"), data)

    def generate_news_list(self):
        all_items = list(self.scraped_urls.values())
        news_list = [v for v in all_items if v.get('type') == 'news']
        data = {
            "articles": news_list
        }
        self.render_to_file("news.html", os.path.join(DOCS_DIR, "news", "index.html"), data)

    def generate_sitemap(self):
        sitemap_path = os.path.join(DOCS_DIR, "sitemap.xml")
        urls = list(self.scraped_urls.keys()) + ["/"]
        
        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%d")
        
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for u in urls:
            full_url = f"https://cuplive.online{u}"
            xml += f'  <url><loc>{full_url}</loc><lastmod>{now}</lastmod></url>\n'
        xml += '</urlset>'
        
        with open(sitemap_path, 'w', encoding='utf-8') as f:
            f.write(xml)

    def generate_live_json(self):
        """Generates a small JSON for the frontend containing only live matches and latest news."""
        live_path = os.path.join(DOCS_DIR, "live.json")
        items = list(self.scraped_urls.values())
        
        # Filter for live matches or today's matches
        import datetime
        today = datetime.date.today().strftime("%Y-%m-%d")
        live_matches = [i for i in items if i['type'] == 'match' and (i.get('live') or i.get('date') == today)]
        
        # Latest 10 news articles
        news = [i for i in items if i['type'] == 'news']
        latest_news = news[-10:] if len(news) >= 10 else news
        
        today_matches = [
            {
                "type": "match",
                "slug": m['slug'],
                "title": m['title'],
                "team_a": m['team_a'],
                "team_b": m['team_b'],
                "league": m['league'],
                "time": m['time'],
                "date": m['date'],
                "live": m.get('live', False),
                "watch_url": m.get('watch_url')
            } for m in live_matches if m.get('watch_url')
        ]
        
        data = {
            "live_matches": today_matches,
            "latest_news": latest_news,
            "last_update": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        with open(live_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        logging.info(f"Generated live.json: {live_path}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # gen = SiteGenerator()
