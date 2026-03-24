"""
591 買賣物件爬蟲 → Notion 自動化
每天早上執行，將新案件寫入 Notion 資料庫
使用 HTML 解析方式，避免 API 被擋
"""

import os
import re
import json
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime, date
from typing import Optional

# ── 設定區 ──────────────────────────────────────────────
NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]

# 591 搜尋條件（可自行調整）
SEARCH_CONFIG = {
    "region": 1,          # 1=台北, 2=新北, 3=桃園, 6=台中, 11=高雄
    "section": "",        # 行政區，留空=全區
    "price_min": 0,       # 最低價（萬元），0=不限
    "price_max": 0,       # 最高價（萬元），0=不限
    "type": "2",          # 2=大樓, 3=華廈, 4=公寓, 6=透天厝（逗號多選）
    "max_pages": 3,       # 最多爬幾頁（每頁30筆）
}

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.5",
    "Referer": "https://sale.591.com.tw/",
}

# ── 591 爬蟲 ──────────────────────────────────────────

def build_search_url(page: int = 1) -> str:
    region = SEARCH_CONFIG["region"]
    house_type = SEARCH_CONFIG["type"]
    price_min = SEARCH_CONFIG["price_min"]
    price_max = SEARCH_CONFIG["price_max"]
    section = SEARCH_CONFIG["section"]
    first_row = (page - 1) * 30

    params = [
        f"regionid={region}",
        f"firstRow={first_row}",
        "order=posttime",
        "orderType=desc",
    ]
    if house_type:
        for t in house_type.split(","):
            params.append(f"kind={t.strip()}")
    if price_min > 0:
        params.append(f"dealTotalPrice_start={price_min}")
    if price_max > 0:
        params.append(f"dealTotalPrice_end={price_max}")
    if section:
        params.append(f"sectionid={section}")

    return f"https://sale.591.com.tw/home/house/index?{'&'.join(params)}"


def get_591_listings() -> list[dict]:
    session = requests.Session()
    session.headers.update(HEADERS)
    all_items = []

    for page in range(1, SEARCH_CONFIG["max_pages"] + 1):
        url = build_search_url(page)
        print(f"📡 爬取第 {page} 頁: {url}")
        try:
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
        except Exception as e:
            print(f"❌ 第 {page} 頁請求失敗: {e}")
            break

        items = parse_json_in_html(resp.text)
        if not items:
            items = parse_html_page(resp.text)

        if not items:
            print(f"📭 第 {page} 頁無資料，停止")
            break

        all_items.extend(items)
        print(f"✅ 第 {page} 頁完成，累計 {len(all_items)} 筆")
        time.sleep(2)

    return all_items


def parse_json_in_html(html: str) -> list[dict]:
    """從頁面內嵌 JSON 解析物件資料"""
    patterns = [
        r'window\.__INITIAL_STATE__\s*=\s*({.+?})\s*;',
        r'window\.__DATA__\s*=\s*({.+?})\s*;',
        r'"house_list"\s*:\s*(\[.+?\])',
    ]
    for pattern in patterns:
        m = re.search(pattern, html, re.DOTALL)
        if not m:
            continue
        try:
            raw = json.loads(m.group(1))
            house_list = find_house_list(raw)
            if house_list:
                items = [parse_house_json(h) for h in house_list]
                return [i for i in items if i]
        except Exception:
            continue
    return []


def find_house_list(data, depth=0) -> list:
    if depth > 6:
        return []
    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        if any(k in data[0] for k in ["houseid", "house_id", "houseId"]):
            return data
    if isinstance(data, dict):
        for key in ["house_list", "list", "items", "data", "result", "rows"]:
            if key in data:
                result = find_house_list(data[key], depth + 1)
                if result:
                    return result
    return []


def parse_house_json(h: dict) -> Optional[dict]:
    house_id = str(h.get("houseid") or h.get("house_id") or h.get("houseId") or "")
    if not house_id:
        return None

    title = h.get("fulladdress") or h.get("address") or h.get("title") or "未知地址"

    price_raw = h.get("price") or h.get("total_price") or h.get("totalPrice") or 0
    try:
        price_wan = float(str(price_raw).replace(",", "").replace("萬", ""))
        if price_wan > 100000:
            price_wan /= 10000
    except:
        price_wan = 0

    area = float(h.get("area") or h.get("ping") or 0)
    unit_price = round(price_wan / area, 1) if area > 0 and price_wan > 0 else 0

    kind_map = {
        "1":"住宅","2":"大樓","3":"華廈","4":"公寓",
        "5":"套房","6":"透天厝","7":"店面","9":"土地"
    }
    house_type = kind_map.get(str(h.get("kind", "")), h.get("kindstr", "買賣"))

    return {
        "id": house_id,
        "title": str(title)[:100],
        "price_wan": round(price_wan, 1),
        "unit_price": unit_price,
        "area": area,
        "pattern": str(h.get("pattern") or h.get("layout") or ""),
        "floor": str(h.get("floor") or ""),
        "location": str(h.get("regionname", "") + h.get("sectionname", "")),
        "post_time": str(h.get("posttime") or h.get("post_time") or ""),
        "url": f"https://sale.591.com.tw/home/house/detail/2/{house_id}.html",
        "image": str(h.get("mainimage") or h.get("image") or ""),
        "house_type": house_type,
    }


def parse_html_page(html: str) -> list[dict]:
    """備用：直接解析 HTML 卡片"""
    soup = BeautifulSoup(html, "html.parser")
    items = []
    cards = (
        soup.select("li.house-item") or
        soup.select("div.house-item") or
        soup.select("[data-houseid]")
    )
    for card in cards:
        try:
            house_id = card.get("data-houseid", "")
            if not house_id:
                link = card.select_one("a[href*='detail']")
                if link:
                    m = re.search(r"/(\d+)\.html", link.get("href", ""))
                    if m:
                        house_id = m.group(1)
            if not house_id:
                continue

            title_el = card.select_one(".house-title, .title, h3, h4")
            title = title_el.get_text(strip=True) if title_el else f"物件{house_id}"

            price_el = card.select_one("[class*='price']")
            price_wan = 0.0
            if price_el:
                m = re.search(r"[\d\.]+", price_el.get_text().replace(",", ""))
                if m:
                    price_wan = float(m.group())

            area = 0.0
            area_el = card.select_one("[class*='area'], [class*='ping']")
            if area_el:
                m = re.search(r"([\d\.]+)\s*坪", area_el.get_text())
                if m:
                    area = float(m.group(1))

            items.append({
                "id": house_id,
                "title": title[:100],
                "price_wan": price_wan,
                "unit_price": round(price_wan / area, 1) if area > 0 else 0,
                "area": area,
                "pattern": "",
                "floor": "",
                "location": "",
                "post_time": "",
                "url": f"https://sale.591.com.tw/home/house/detail/2/{house_id}.html",
                "image": "",
                "house_type": "買賣",
            })
        except Exception:
            continue
    return items


# ── Notion 寫入 ──────────────────────────────────────────

def get_existing_ids() -> set[str]:
    ids = set()
    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    payload = {
        "page_size": 100,
        "filter": {"property": "物件ID", "rich_text": {"is_not_empty": True}},
    }
    try:
        resp = requests.post(url, headers=NOTION_HEADERS, json=payload, timeout=15)
        for page in resp.json().get("results", []):
            rt = page.get("properties", {}).get("物件ID", {}).get("rich_text", [])
            if rt:
                ids.add(rt[0]["plain_text"])
    except Exception as e:
        print(f"⚠️  取得既有 ID 失敗: {e}")
    return ids


def create_notion_page(item: dict) -> bool:
    url = "https://api.notion.com/v1/pages"
    props = {
        "物件名稱": {"title": [{"text": {"content": item["title"]}}]},
        "物件ID":   {"rich_text": [{"text": {"content": item["id"]}}]},
        "類型":     {"select": {"name": item["house_type"]}},
        "格局":     {"rich_text": [{"text": {"content": item["pattern"]}}]},
        "樓層":     {"rich_text": [{"text": {"content": item["floor"]}}]},
        "地區":     {"rich_text": [{"text": {"content": item["location"]}}]},
        "上架時間": {"rich_text": [{"text": {"content": item["post_time"]}}]},
        "591連結":  {"url": item["url"]},
        "狀態":     {"select": {"name": "📥 待確認"}},
        "蒐集日期": {"date": {"start": date.today().isoformat()}},
    }
    if item["price_wan"] > 0:
        props["售價（萬）"] = {"number": item["price_wan"]}
    if item["unit_price"] > 0:
        props["單價（萬/坪）"] = {"number": item["unit_price"]}
    if item["area"] > 0:
        props["坪數"] = {"number": item["area"]}

    payload = {"parent": {"database_id": NOTION_DATABASE_ID}, "properties": props}
    if item.get("image") and item["image"].startswith("http"):
        payload["cover"] = {"type": "external", "external": {"url": item["image"]}}

    try:
        resp = requests.post(url, headers=NOTION_HEADERS, json=payload, timeout=15)
        if resp.status_code == 200:
            return True
        print(f"❌ Notion 寫入失敗 [{resp.status_code}]: {resp.text[:300]}")
        return False
    except Exception as e:
        print(f"❌ Notion 請求錯誤: {e}")
        return False


# ── 主程式 ───────────────────────────────────────────────

def main():
    print(f"\n{'='*50}")
    print(f"🏠 591 買賣物件自動蒐集")
    print(f"⏰ 執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}\n")

    print("📡 開始爬取 591...")
    listings = get_591_listings()
    print(f"\n📦 共取得 {len(listings)} 筆物件\n")

    if not listings:
        print("⚠️  無新物件，結束")
        return

    print("🔍 檢查 Notion 已有資料...")
    existing = get_existing_ids()
    print(f"   已有 {len(existing)} 筆紀錄\n")

    new_count, skip_count = 0, 0
    for item in listings:
        if item["id"] in existing:
            skip_count += 1
            continue
        if create_notion_page(item):
            new_count += 1
            print(f"  ✅ [{new_count}] {item['title']} | {item['price_wan']}萬 | {item['area']}坪")
        time.sleep(0.4)

    print(f"\n{'='*50}")
    print(f"🎉 完成！新增 {new_count} 筆，略過 {skip_count} 筆重複")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
