import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from feedgen.feed import FeedGenerator

LIST_URL = "https://www.npic.ac.cn/hdly/jyzp/yjszs/index.html"
RSS_FILE = "rss.xml"
TZ_CN = timezone(timedelta(hours=8))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def load_existing_dates(filepath: str) -> dict[str, datetime]:
    dates = {}
    if not os.path.exists(filepath):
        return dates
    try:
        tree = ET.parse(filepath)
        for item in tree.findall(".//item"):
            link_el = item.find("link")
            pub_el = item.find("pubDate")
            if link_el is not None and pub_el is not None and link_el.text and pub_el.text:
                dates[link_el.text.strip()] = date_parser.parse(pub_el.text.strip())
    except Exception:
        pass
    return dates


def extract_date(text: str) -> datetime | None:
    m = re.search(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})", text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return datetime(y, mo, d, 9, 0, 0, tzinfo=TZ_CN)
    return None


def main():
    existing_dates = load_existing_dates(RSS_FILE)

    resp = requests.get(LIST_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"

    soup = BeautifulSoup(resp.text, "html.parser")

    items_data = []
    seen_links = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        title = a.get_text(" ", strip=True)
        if not title or len(title) < 4:
            continue

        full_url = urljoin(LIST_URL, href)
        path = urlparse(full_url).path
        filename = os.path.basename(path)

        if "/hdly/jyzp/yjszs/" not in path or not filename.endswith(".html"):
            continue
        if filename.startswith("index"):
            continue
        if full_url in seen_links:
            continue
        seen_links.add(full_url)

        parent_text = a.parent.get_text(" ", strip=True) if a.parent else title
        pub_date = extract_date(parent_text) or existing_dates.get(full_url) or datetime.now(TZ_CN)

        items_data.append({
            "title": title,
            "link": full_url,
            "pubDate": pub_date,
        })

    if not items_data:
        raise RuntimeError("未抓取到任何有效文章链接，请检查网页结构或访问连通性。")

    fg = FeedGenerator()
    fg.id(LIST_URL)
    fg.title("中国核动力研究设计院 - 研究生招生公告")
    fg.link(href=LIST_URL, rel="alternate")
    fg.description("自动追踪中国核动力研究设计院研究生招生栏目更新")
    fg.language("zh-CN")

    for entry in items_data[:30]:
        fe = fg.add_entry()
        fe.id(entry["link"])
        fe.title(entry["title"])
        fe.link(href=entry["link"])
        fe.pubDate(entry["pubDate"])
        fe.description(f'<p><a href="{entry["link"]}">{entry["title"]}</a></p>')

    fg.rss_file(RSS_FILE, pretty=True)
    print(f"成功生成 {RSS_FILE}，共收录 {len(items_data[:30])} 条公告。")


if __name__ == "__main__":
    main()
