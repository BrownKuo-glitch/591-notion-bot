"""
591 買賣物件爬蟲 → Notion 自動化
每天早上執行，將新案件寫入 Notion 資料庫
"""

import os
import json
import time
import hashlib
import requests
from datetime import datetime, date
from typing import Optional

# ── 設定區 ──────────────────────────────────────────────
NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]

# 591 搜尋條件（可自行調整）
SEARCH_CONFIG = {
    "region": 1,          # 1=台北, 3=桃園, 6=台中, 11=高雄（可改成你負責的區域）
    "section": "",        # 行政區，留空=全區
    "price_min": 0,       # 最低價（萬元）
    "price_max": 0,       # 最高價（萬元），0=不限
    "type": "2",          # 1=住宅, 2=大樓, 3=華廈, 4=公寓, 6=透天厝（可用逗號多選）
    "max_pages": 3,       # 最多爬幾頁（每頁30筆）
}

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

# ── 591 爬蟲 ────────────────────────────────────────────

def get_591_listings() -> list[dict]:
    """爬取 591 買賣物件列表"""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://sale.591.com.tw/",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-TW,zh;q=0.9",
    })

    # 取得 CSRF token
    try:
        r = session.get("https://sale.591.com.tw/", timeout=15)
        csrf_token = session.cookies.get("csrf_token", "")
        if csrf_token:
            session.headers["X-CSRF-TOKEN"] = csrf_token
    except Exception as e:
        print(f"⚠️  取得 CSRF token 失敗: {e}")

    all_items = []
    today_str = date.today().isoformat()

    for page in range(1, SEARCH_CONFIG["max_pages"] + 1):
        params = {
            "type": "2",          # 買賣
            "region": SEARCH_CONFIG["region"],
            "firstRow": (page - 1) * 30,
            "totalRows": 30,
            "order": "posttime",  # 依上架時間排序（最新優先）
            "orderType": "desc",
            "houseType": SEARCH_CONFIG["type"],
        }

        if SEARCH_CONFIG["section"]:
            params["section"] = SEARCH_CONFIG["section"]
        if SEARCH_CONFIG["price_min"] > 0:
            params["dealPrice_start"] = SEARCH_CONFIG["price_min"] * 10000
        if SEARCH_CONFIG["price_max"] > 0:
            params["dealPrice_end"] = SEARCH_CONFIG["price_max"] * 10000

        try:
            resp = session.get(
                "https://bff.591.com.tw/v1/house/sell/list",
                params=params,
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"❌ 第 {page} 頁請求失敗: {e}")
            break

        houses = data.get("data", {}).get("house_list", [])
        if not houses:
            print(f"📭 第 {page} 頁無資料，停止")
            break

        for h in houses:
            post_time = h.get("posttime", "")
            # 只取今天上架的（早上執行時抓昨日以來的新案也可，視需求調整）
            item = parse_house(h)
            if item:
                all_items.append(item)

        print(f"✅ 第 {page} 頁完成，累計 {len(all_items)} 筆")
        time.sleep(1.5)  # 避免請求過快

    return all_items


def parse_house(h: dict) -> Optional[dict]:
    """解析單筆物件資料"""
    try:
        house_id = str(h.get("houseid", ""))
        title = h.get("fulladdress", h.get("address", "未知地址"))
        price_raw = h.get("price", 0)

        # 價格處理（591 回傳單位為元）
        if isinstance(price_raw, str):
            price_raw = price_raw.replace(",", "").replace("萬", "")
            try:
                price_wan = float(price_raw)
            except:
                price_wan = 0
        else:
            price_wan = float(price_raw) / 10000 if price_raw > 10000 else float(price_raw)

        kind_map = {
            "1": "住宅", "2": "大樓", "3": "華廈",
            "4": "公寓", "5": "套房", "6": "透天厝",
            "7": "店面", "8": "辦公", "9": "土地", "10": "車位",
        }
        house_type = kind_map.get(str(h.get("kind", "")), h.get("kindstr", "其他"))

        area = h.get("area", 0)       # 坪數
        floor = h.get("floor", "")    # 樓層
        pattern = h.get("pattern", "") # 格局，如 3房2廳

        post_time = h.get("posttime", "")
        region_name = h.get("regionname", "")
        section_name = h.get("sectionname", "")
        location = f"{region_name}{section_name}"

        url = f"https://sale.591.com.tw/home/house/detail/2/{house_id}.html"

        return {
            "id": house_id,
            "title": title,
            "price_wan": round(price_wan, 1),
            "house_type": house_type,
            "area": float(area) if area else 0,
            "floor": str(floor),
            "pattern": pattern,
            "location": location,
            "post_time": post_time,
            "url": url,
            "image": h.get("mainimage", ""),
        }
    except Exception as e:
        print(f"⚠️  解析物件失敗: {e}")
        return None


# ── Notion 寫入 ──────────────────────────────────────────

def get_existing_ids() -> set[str]:
    """從 Notion 取得已存在的物件 ID，避免重複"""
    ids = set()
    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    payload = {
        "page_size": 100,
        "filter": {"property": "物件ID", "rich_text": {"is_not_empty": True}},
    }
    try:
        resp = requests.post(url, headers=NOTION_HEADERS, json=payload, timeout=15)
        for page in resp.json().get("results", []):
            prop = page.get("properties", {}).get("物件ID", {})
            rt = prop.get("rich_text", [])
            if rt:
                ids.add(rt[0]["plain_text"])
    except Exception as e:
        print(f"⚠️  取得既有 ID 失敗: {e}")
    return ids


def create_notion_page(item: dict) -> bool:
    """在 Notion 資料庫建立一筆物件頁面"""
    url = "https://api.notion.com/v1/pages"

    # 單價（萬/坪）
    unit_price = round(item["price_wan"] / item["area"], 1) if item["area"] > 0 else 0

    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "物件名稱": {
                "title": [{"text": {"content": item["title"][:100]}}]
            },
            "物件ID": {
                "rich_text": [{"text": {"content": item["id"]}}]
            },
            "售價（萬）": {
                "number": item["price_wan"]
            },
            "單價（萬/坪）": {
                "number": unit_price
            },
            "坪數": {
                "number": item["area"]
            },
            "類型": {
                "select": {"name": item["house_type"]}
            },
            "格局": {
                "rich_text": [{"text": {"content": item["pattern"]}}]
            },
            "樓層": {
                "rich_text": [{"text": {"content": item["floor"]}}]
            },
            "地區": {
                "rich_text": [{"text": {"content": item["location"]}}]
            },
            "上架時間": {
                "rich_text": [{"text": {"content": item["post_time"]}}]
            },
            "591連結": {
                "url": item["url"]
            },
            "狀態": {
                "select": {"name": "📥 待確認"}
            },
            "蒐集日期": {
                "date": {"start": date.today().isoformat()}
            },
        },
    }

    # 加入封面圖（若有）
    if item.get("image"):
        payload["cover"] = {"type": "external", "external": {"url": item["image"]}}

    try:
        resp = requests.post(url, headers=NOTION_HEADERS, json=payload, timeout=15)
        if resp.status_code == 200:
            return True
        else:
            print(f"❌ Notion 寫入失敗 [{resp.status_code}]: {resp.text[:200]}")
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

    # 1. 爬取 591
    print("📡 開始爬取 591...")
    listings = get_591_listings()
    print(f"\n📦 共取得 {len(listings)} 筆物件\n")

    if not listings:
        print("⚠️  無新物件，結束")
        return

    # 2. 取得 Notion 已有 ID
    print("🔍 檢查 Notion 已有資料...")
    existing = get_existing_ids()
    print(f"   已有 {len(existing)} 筆紀錄\n")

    # 3. 寫入新物件
    new_count = 0
    skip_count = 0

    for item in listings:
        if item["id"] in existing:
            skip_count += 1
            continue

        success = create_notion_page(item)
        if success:
            new_count += 1
            print(f"  ✅ [{new_count}] {item['title']} | {item['price_wan']}萬 | {item['area']}坪")
        time.sleep(0.4)  # Notion API rate limit

    print(f"\n{'='*50}")
    print(f"🎉 完成！新增 {new_count} 筆，略過 {skip_count} 筆重複")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
