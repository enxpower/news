# fetch_feeds.py
# 固化要求：
# - 每源最多 30 条（PER_FEED_LIMIT）
# - 源若 30 天无更新则跳过（STALE_DAYS）
# - 生成 data/news.json 与 data/meta.json
# - 不因单源失败导致脚本报错退出

import os
import json
import feedparser
from datetime import datetime, timezone, timedelta

# ---------- 可调参数（也可用环境变量覆盖） ----------
STALE_DAYS = int(os.getenv("STALE_DAYS", "30"))
PER_FEED_LIMIT = int(os.getenv("PER_FEED_LIMIT", "30"))
TOTAL_LIMIT = int(os.getenv("TOTAL_LIMIT", "200"))
USER_AGENT = os.getenv("FEED_USER_AGENT", "Mozilla/5.0 (compatible; BESSNewsBot/1.2; +https://example.org)")
# ---------------------------------------------------

feedparser.USER_AGENT = USER_AGENT

def load_feeds() -> list[str]:
    """优先 data/feeds.json，其次根目录 feeds.json；支持 ['url', ...] 或 [{'url': '...'}]"""
    for path in ("data/feeds.json", "feeds.json"):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            feeds = []
            if isinstance(data, list):
                for it in data:
                    if isinstance(it, str):
                        feeds.append(it.strip())
                    elif isinstance(it, dict) and "url" in it:
                        feeds.append(str(it["url"]).strip())
            return [u for u in feeds if u]
    print("⚠️ 未找到 feeds 列表（data/feeds.json 或 feeds.json）")
    return []

def pick_date(entry):
    """尽量从 entry 中取出 UTC 日期"""
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        if entry.get(key):
            try:
                return datetime(*entry[key][:6], tzinfo=timezone.utc)
            except Exception:
                pass
    for key in ("published", "updated", "created"):
        val = entry.get(key)
        if isinstance(val, str) and len(val) >= 10:
            try:
                # 常见格式 YYYY-MM-DD...
                return datetime.fromisoformat(val[:10] + "T00:00:00+00:00")
            except Exception:
                pass
    return None

def date_to_str(d):
    return d.astimezone(timezone.utc).strftime("%Y-%m-%d") if d else ""

def clean_summary(txt: str) -> str:
    if not txt:
        return ""
    t = txt.replace("\n", " ").replace("\r", " ")
    for tag in ("<p>", "</p>", "<br>", "<br/>", "<br />"):
        t = t.replace(tag, " ")
    t = " ".join(t.split())
    return (t[:140] + "…") if t else ""

def extract_image(entry) -> str | None:
    try:
        if "media_thumbnail" in entry and entry.media_thumbnail:
            url = entry.media_thumbnail[0].get("url")
            if url: return url
        if "media_content" in entry and entry.media_content:
            for m in entry.media_content:
                if m.get("medium") == "image" or str(m.get("type","")).startswith("image/"):
                    if m.get("url"): return m["url"]
        if "links" in entry and entry.links:
            for l in entry.links:
                if str(l.get("type","")).startswith("image/") and l.get("href"):
                    return l["href"]
        if "itunes_image" in entry and entry.itunes_image.get("href"):
            return entry.itunes_image["href"]
        if "image" in entry and isinstance(entry.image, dict) and entry.image.get("href"):
            return entry.image["href"]
    except Exception:
        pass
    return None

def main():
    feeds = load_feeds()
    now_utc = datetime.now(timezone.utc)
    stale_cutoff = now_utc - timedelta(days=STALE_DAYS)

    stats = {
        "total_sources": len(feeds),
        "used_sources": 0,
        "skipped_stale": 0,
        "errors": 0,
        "items_before_dedup": 0
    }

    all_items = []
    seen_links = set()

    for url in feeds:
        try:
            feed = feedparser.parse(url)
            entries = list(feed.entries or [])
            if not entries:
                # 空源：按无更新处理
                stats["skipped_stale"] += 1
                continue

            # 判断该源最近是否有更新
            latest_dt = None
            for e in entries:
                d = pick_date(e)
                if d and (latest_dt is None or d > latest_dt):
                    latest_dt = d

            if (latest_dt is None) or (latest_dt < stale_cutoff):
                # 超过 STALE_DAYS 无更新：跳过
                stats["skipped_stale"] += 1
                continue

            # 限制每源条数
            entries = entries[:PER_FEED_LIMIT]
            source = feed.feed.get("title", "RSS Source")

            for e in entries:
                link = (e.get("link") or "").strip()
                title = (e.get("title") or "").strip()
                if not link or not title:
                    continue
                if link.lower() in seen_links:
                    continue

                item = {
                    "title": title,
                    "link": link,
                    "date": date_to_str(pick_date(e)),
                    "summary": clean_summary(e.get("summary", "")),
                    "source": source,
                    "image": extract_image(e)
                }
                all_items.append(item)
                seen_links.add(link.lower())

            stats["used_sources"] += 1

        except Exception as ex:
            stats["errors"] += 1
            print(f"❌ 解析失败：{url} -> {ex}")

    stats["items_before_dedup"] = len(all_items)

    # 全局排序与总量裁剪
    all_items.sort(key=lambda x: x.get("date",""), reverse=True)
    if TOTAL_LIMIT and len(all_items) > TOTAL_LIMIT:
        all_items = all_items[:TOTAL_LIMIT]

    os.makedirs("data", exist_ok=True)

    with open("data/news.json", "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)

    meta = {
        "updated": now_utc.strftime("%Y-%m-%d %H:%M UTC"),
        "count": len(all_items),
        "stats": stats,
        "config": {
            "stale_days": STALE_DAYS,
            "per_feed_limit": PER_FEED_LIMIT,
            "total_limit": TOTAL_LIMIT
        }
    }
    with open("data/meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print("✅ 聚合完成")
    print(json.dumps(meta, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
