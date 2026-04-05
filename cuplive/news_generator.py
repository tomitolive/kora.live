import anthropic
import logging
from config import CLAUDE_API_KEY, CLAUDE_MODEL

class NewsGenerator:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    def generate_article(self, headline):
        logging.info(f"Generating professional article for: {headline}")
        prompt = f"""
        أنت صحفي رياضي خبير في موقع CupLive. اكتب مقالاً إخبارياً احترافياً باللغة العربية الفصحى.
        العنوان: {headline}

        هيكل المقال:
        1. مقدمة قوية تلخص الخبر.
        2. ثلاثة فقرات مفصلة تحتوي على خلفية الخبر، تفاصيل الحدث، وتحليل سريع.
        3. خاتمة تلخص التوقعات المستقبلية.

        المتطلبات:
        - أسلوب صحفي رصين (مثل الجزيرة الرياضية أو beIN Sports).
        - استخدام علامات ترقيم صحيحة.
        - التنسيق باستخدام وسوم HTML بسيطة (h2, p, strong).
        - لا تذكر أنك ذكاء اصطناعي، اكتب مباشرة كصحفي في CupLive.
        """
        
        try:
            response = self.client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        except Exception as e:
            logging.error(f"Claude API Error: {e}")
            return f"<p>عذراً، تعذر توليد المقال حالياً. {headline}</p>"

if __name__ == "__main__":
    # gen = NewsGenerator()
    pass
