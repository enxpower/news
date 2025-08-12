# aggregator.py
# 作用：
# - 读取 feeds 列表（优先 data/feeds.json，其次根目录 feeds.json）
# - 每个源最多取 30 条（超过自动截断）
# - 若源最近无更新（默认 30 天内无新条目）则跳过该源（不报错）
# - 自动去重（按 link），清洗摘要，尝试提取图片
# - 生成 data/news.json 与 data/meta.json
# - 任何单个源失败都只计入统计，不中断脚本（确保 workflow 不会 fail）

import os
import json
import feedparser
from datetime import datetime, timezone, timedelta

# ---------- 可调参数 ----------
STALE_DAYS = int(os.getenv("STALE_DAYS", "30"))     # 源若在此天数内无更新，则视为“无更新”并跳过
PER_FEED_LIMIT = int(os.getenv("PER_FEED_LIMIT", "30"))  # 每个源最多条数
TOTAL_LIMIT = int(os.getenv("TOTAL_LIMIT", "200"))  # 聚合后总条数上限
USER_AGENT = os.getenv("FEED_USER_AGENT", "Mozilla/5.0 (compatible; BESSNewsBot/1.2; +https://example.org)")
# -----------------------------

feedparser.USER_AGENT = USER_AGENT

def load_feeds() -> list[str]:
    candidates = ["data/feeds.json", "feeds.json"]
    for path in candidates:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 既支持 ["url", ...] 也支持 [{"url": "..."}]
            feeds = []
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, str):
                        feeds.append(item.strip())
                    elif isinstance(item, dict) and "url" in item:
                        feeds.append(item["url"].strip())
            return [u for u in feeds if u]
    print("⚠️ 未找到 feeds 列表（尝试了 data/feeds.json 和 feeds.json）")
    return []

def pick_date(entry) -> datetime | None:
    # 1) *_parsed
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        if entry.get(key):
            try:
                return datetime(*entry[key][:6], tzinfo=timezone.utc)
            except Exception:
                pass
    # 2) 文本字段兜底
    for key in ("published", "updated", "created"):
        val = entry.get(key)
        if isinstance(val, str) and len(val) >= 10:
            try:
                # 常见格式：YYYY-MM-DD...
                return datetime.fromisoformat(val[:10] + "T00:00:00+00:00")
            except Exception:
                # 尝试 RFC2822 解析（feedparser 通常会给 parsed，不走到这里）
                pass
    return None

def date_to_str(d: datetime | None) -> str:
    if not d:
        return ""
    return d.astimezone(timezone.utc).strftime("%Y-%m-%d")

def clean_summary(txt: str) -> str:
    if not txt:
        return ""
    t = txt.replace("\n", " ").replace("\r", " ")
    # 粗糙去标签
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
            # 某些异常时 feed.bozo == 1，但仍可能有 entries；这里不据此直接失败
            entries = list(feed.entries or [])
            if not entries:
                # 空源：当作“无更新”，跳过
                stats["skipped_stale"] += 1
                continue

            # 以最新一条的时间判断这条源是否“近期有更新”
            # 取 entries 中有日期的最大值
            latest_dt = None
            for e in entries:
                d = pick_date(e)
                if d and (latest_dt is None or d > latest_dt):
                    latest_dt = d

            if (latest_dt is None) or (latest_dt < stale_cutoff):
                # 最近 STALE_DAYS 内无更新
                stats["skipped_stale"] += 1
                continue

            # 该源可用：限制每源最多 PER_FEED_LIMIT 条
            entries = entries[:PER_FEED_LIMIT]
            source = feed.feed.get("title", "RSS Source")

            for e in entries:
                link = (e.get("link") or "").strip()
                title = (e.get("title") or "").strip()
                if not link or not title:
                    continue

                if link.lower() in seen_links:
                    continue

                d = pick_date(e)
                item = {
                    "title": title,
                    "link": link,
                    "date": date_to_str(d),
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

    # 按日期倒序并总体裁剪
    all_items.sort(key=lambda x: x.get("date",""), reverse=True)
    if TOTAL_LIMIT and len(all_items) > TOTAL_LIMIT:
        all_items = all_items[:TOTAL_LIMIT]

    # 确保输出目录存在
    os.makedirs("data", exist_ok=True)

    # 写 news.json
    with open("data/news.json", "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)

    # 写 meta.json（包含统计与更新时间）
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

    # 友好日志（不以异常结束，保证 workflow 成功）
    print("✅ 聚合完成")
    print(json.dumps(meta, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
