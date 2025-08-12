import json
import feedparser
from datetime import datetime, timezone

# 让部分站点更愿意返回内容
feedparser.USER_AGENT = "Mozilla/5.0 (compatible; BESSNewsBot/1.1; +https://news.example)"

with open("feeds.json", "r", encoding="utf-8") as f:
    FEEDS = json.load(f)

def pick_date(entry):
    for k in ("published_parsed", "updated_parsed"):
        if entry.get(k):
            return datetime(*entry[k][:6]).strftime("%Y-%m-%d")
    for k in ("published", "updated"):
        if entry.get(k):
            return entry[k][:10]
    return ""

def clean_summary(txt: str) -> str:
    if not txt:
        return ""
    t = txt.replace("\n", " ").replace("\r", " ")
    # 很轻量的标签清理
    for tag in ("<p>", "</p>", "<br>", "<br/>", "<br />"):
        t = t.replace(tag, " ")
    t = " ".join(t.split())
    return (t[:140] + "…") if len(t) > 0 else ""

def extract_image(entry) -> str | None:
    """
    仅使用 RSS 内自带图片（最稳妥、最快）。
    优先级：media_thumbnail → media_content → enclosure(link type=image/*) → itunes_image → image
    """
    try:
        # 1) <media:thumbnail>
        if "media_thumbnail" in entry and entry.media_thumbnail:
            url = entry.media_thumbnail[0].get("url")
            if url: return url

        # 2) <media:content>
        if "media_content" in entry and entry.media_content:
            # 选第一张图片类型
            for m in entry.media_content:
                if m.get("medium") == "image" or str(m.get("type","")).startswith("image/"):
                    if m.get("url"): return m["url"]

        # 3) enclosure 链接里找 image/*
        if "links" in entry and entry.links:
            for l in entry.links:
                if str(l.get("type","")).startswith("image/") and l.get("href"):
                    return l["href"]

        # 4) itunes:image / image
        if "itunes_image" in entry and entry.itunes_image.get("href"):
            return entry.itunes_image["href"]
        if "image" in entry and isinstance(entry.image, dict) and entry.image.get("href"):
            return entry.image["href"]
    except Exception:
        pass
    return None

all_items = []
seen = set()  # 去重（按 link）

for url in FEEDS:
    try:
        feed = feedparser.parse(url)
        source = feed.feed.get("title", "RSS Source")
        for e in feed.entries[:10]:
            link = (e.get("link") or "").strip()
            title = (e.get("title") or "").strip()
            if not link or not title:
                continue
            key = link.lower()
            if key in seen:
                continue
            seen.add(key)

            item = {
                "title": title,
                "link": link,
                "date": pick_date(e),
                "summary": clean_summary(e.get("summary", "")),
                "source": source,
                "image": extract_image(e)  # 新增字段
            }
            all_items.append(item)
    except Exception as ex:
        print(f"❌ Parse failed: {url} -> {ex}")

# 排序 & 裁剪
all_items.sort(key=lambda x: x["date"], reverse=True)
all_items = all_items[:100]

# 写 news.json
with open("data/news.json", "w", encoding="utf-8") as f:
    json.dump(all_items, f, ensure_ascii=False, indent=2)
print(f"✅ Wrote {len(all_items)} items to data/news.json")

# 写 meta.json（UTC）
updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
with open("data/meta.json", "w", encoding="utf-8") as f:
    json.dump({"updated": updated, "count": len(all_items)}, f, ensure_ascii=False, indent=2)
print("✅ Wrote data/meta.json")
