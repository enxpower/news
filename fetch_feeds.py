import json
import feedparser
from datetime import datetime, timezone

# 给部分站点一个“像浏览器”的UA，提升兼容性
feedparser.USER_AGENT = "Mozilla/5.0 (compatible; BESSNewsBot/1.0; +https://news.example)"

# 读取 RSS 列表
with open("feeds.json", "r", encoding="utf-8") as f:
    FEEDS = json.load(f)

def pick_date(entry):
    # 尽可能取到规范日期
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
    # 简单去除标签
    t = t.replace("<p>", " ").replace("</p>", " ")
    return (t.strip()[:140] + "…") if len(t.strip()) > 0 else ""

all_items = []
seen = set()  # 用于去重（按链接）

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
                "source": source
            }
            all_items.append(item)
    except Exception as ex:
        print(f"❌ Parse failed: {url} -> {ex}")

# 排序并裁剪（最多输出 100 条）
all_items.sort(key=lambda x: x["date"], reverse=True)
all_items = all_items[:100]

# 输出 news.json
with open("data/news.json", "w", encoding="utf-8") as f:
    json.dump(all_items, f, ensure_ascii=False, indent=2)
print(f"✅ Wrote {len(all_items)} items to data/news.json")

# 输出 meta.json（时间为 UTC）
updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
with open("data/meta.json", "w", encoding="utf-8") as f:
    json.dump({"updated": updated, "count": len(all_items)}, f, ensure_ascii=False, indent=2)
print("✅ Wrote data/meta.json")
