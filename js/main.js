// 引入 rss-parser（你必须在 index.html 中提前加载）
const parser = new RSSParser();

const container = document.getElementById("news-container");
const loading = document.getElementById("loading");

async function loadFeeds() {
  loading.innerText = "🔄 正在加载新闻，请稍候…";

  let allItems = [];

  for (const url of FEED_URLS) {
    try {
      const feed = await parser.parseURL(`https://api.rss2json.com/v1/api.json?rss_url=${encodeURIComponent(url)}`);
      const items = feed.items.slice(0, 5).map(item => ({
        title: item.title,
        link: item.link,
        date: item.pubDate?.slice(0, 10) || '',
        summary: item.description?.slice(0, 100) + '…' || '',
        source: feed.feed?.title || 'RSS Source'
      }));
      allItems = allItems.concat(items);
    } catch (err) {
      console.error(`❌ 加载失败: ${url}`, err);
    }
  }

  allItems.sort((a, b) => new Date(b.date) - new Date(a.date));

  container.innerHTML = ""; // 清空旧内容
  allItems.forEach(item => {
    const card = document.createElement("div");
    card.className = "news-card";
    card.innerHTML = `
      <h3><a href="${item.link}" target="_blank">${item.title}</a></h3>
      <p class="meta">${item.source} · ${item.date}</p>
      <p>${item.summary}</p>
    `;
    container.appendChild(card);
  });

  loading.style.display = "none";
}

loadFeeds();

