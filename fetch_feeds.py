import json
import feedparser
from datetime import datetime

with open("feeds.json", "r", encoding="utf-8") as f:
    feed_urls = json.load(f)

all_news = []

for url in feed_urls:
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:5]:
            item = {
                "title": entry.get("title", "").strip(),
                "link": entry.get("link", "").strip(),
                "date": entry.get("published", "")[:10],
                "summary": entry.get("summary", "").strip().replace("\n", " ").replace("\r", "")[:100] + "…",
                "source": feed.feed.get("title", "RSS Source")
            }
            all_news.append(item)
    except Exception as e:
        print(f"❌ Failed to parse {url}: {e}")

# 按日期倒序排列
all_news.sort(key=lambda x: x["date"], reverse=True)

with open("data/news.json", "w", encoding="utf-8") as f:
    json.dump(all_news, f, ensure_ascii=False, indent=2)

print(f"✅ Successfully wrote {len(all_news)} items to data/news.json")

