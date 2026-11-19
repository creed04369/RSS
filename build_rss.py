import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from feedgen.feed import FeedGenerator
from playwright.sync_api import sync_playwright

LIST_URL = "https://www.npic.ac.cn/hdly/jyzp/yjszs/index.html"
RSS_FILE = "rss.xml"
TZ_CN = timezone(timedelta(hours=8))


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


def fetch_all_frames_html(url: str) -> list[tuple[str, str]]:
    """获取主页面以及所有 iframe 子页面的 HTML"""
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            locale="zh-CN",
        )
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=45000)
        page.wait_for_timeout(3000)

        print("页面标题:", page.title())
        for frame in page.frames:
            try:
                results.append((frame.url or url, frame.content()))
            except Exception:
                pass
        browser.close()
    return results


def main():
    existing_dates = load_existing_dates(RSS_FILE)
    frames_html = fetch_all_frames_html(LIST_URL)

    items_data = []
    seen_links = set()
    sample_links = []

    for base_url, html in frames_html:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            title = a.get("title") or a.get_text(" ", strip=True)
            title = " ".join(title.split())
            if not title or len(title) < 6:
                continue

            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)
            if "npic.ac.cn" not in parsed.netloc:
                continue

            path = parsed.path
            filename = os.path.basename(path)
            sample_links.append(f"{title} -> {full_url}")

            # 排除首页、栏目列表页及翻页链接，保留具体文章详情页
            if not filename or filename.startswith("index"):
                continue
            if not any(filename.endswith(ext) for ext in (".html", ".htm", ".shtml", ".jsp", ".aspx")):
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
        print("调试样例链接（前15条）:")
        for s in sample_links[:15]:
            print("  ", s)
        raise RuntimeError("未抓取到任何有效文章链接，请查看上方日志中的页面标题与样例链接。")

    fg = FeedGenerator()
    fg.id(LIST_URL)
    fg.title("中国核动力研究设计院 - 研究生招生公告")
    fg.link(href=LIST_URL, rel="alternate")
    fg.description("自动追踪中国核动力研究设计院“研究生招生”栏目全部公告更新")
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
