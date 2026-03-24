# 🏠 591 買賣物件自動蒐集 → Notion

每天早上 8:00 自動爬取 591 買賣新案，整理後寫入你的 Notion 資料庫。

---

## 📁 檔案結構

```
591-notion-bot/
├── scraper.py                        # 主程式（爬蟲 + Notion 寫入）
├── requirements.txt                  # Python 套件
├── .github/
│   └── workflows/
│       └── daily-scrape.yml          # GitHub Actions 排程設定
└── README.md
```

---

## 🗂️ STEP 1：建立 Notion 資料庫

1. 在 Notion 建立一個新的**資料庫（Database）**，命名如「591 買賣物件」
2. 加入以下欄位（**欄位名稱必須完全一致**）：

| 欄位名稱 | 類型 | 說明 |
|---|---|---|
| 物件名稱 | Title | 地址（自動填入）|
| 物件ID | Text | 591 唯一編號，防重複 |
| 售價（萬） | Number | 總價 |
| 單價（萬/坪） | Number | 自動計算 |
| 坪數 | Number | 建坪 |
| 類型 | Select | 大樓/華廈/公寓… |
| 格局 | Text | 如 3房2廳1衛 |
| 樓層 | Text | 如 5F/12F |
| 地區 | Text | 縣市+行政區 |
| 上架時間 | Text | 591 顯示時間 |
| 591連結 | URL | 直接點開物件頁 |
| 狀態 | Select | 📥待確認 / ✅已聯繫 / ❌不適合 |
| 蒐集日期 | Date | 程式執行當天 |

3. 從資料庫頁面網址取得 **Database ID**（網址中 32 碼英數字串）：
   ```
   https://notion.so/你的名字/XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX?v=...
                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                              這段就是 Database ID
   ```

---

## 🔑 STEP 2：取得 Notion API Token

1. 前往 https://www.notion.so/my-integrations
2. 點「+ New integration」，名稱填 `591Bot`，關聯你的 workspace
3. 複製 **Internal Integration Token**（`secret_...` 開頭）
4. 回到你的 Notion 資料庫頁面 → 右上角「...」→「Connections」→ 加入 `591Bot`

---

## 🐙 STEP 3：上傳到 GitHub

1. 建立一個 **private** repository（建議設私人）
2. 把所有檔案上傳（或用 `git push`）
3. 進入 repo → **Settings → Secrets and variables → Actions**
4. 新增兩個 Secret：
   - `NOTION_TOKEN` → 貼上步驟 2 的 token
   - `NOTION_DATABASE_ID` → 貼上步驟 1 的 Database ID

---

## ⚙️ STEP 4：調整搜尋條件

編輯 `scraper.py` 頂部的 `SEARCH_CONFIG`：

```python
SEARCH_CONFIG = {
    "region": 1,       # 1=台北, 3=桃園, 6=台中, 11=高雄
    "section": "",     # 行政區代碼，留空=全區
    "price_min": 0,    # 最低價（萬），0=不限
    "price_max": 3000, # 最高價（萬），0=不限
    "type": "2",       # 2=大樓, 3=華廈, 4=公寓（逗號可多選，如"2,3,4"）
    "max_pages": 3,    # 爬幾頁（每頁30筆，3頁=90筆）
}
```

**region 代碼對照：**
| 代碼 | 縣市 |
|---|---|
| 1 | 台北市 |
| 2 | 新北市 |
| 3 | 桃園市 |
| 4 | 新竹縣市 |
| 5 | 苗栗縣 |
| 6 | 台中市 |
| 10 | 台南市 |
| 11 | 高雄市 |

---

## ▶️ STEP 5：測試執行

1. 進入 GitHub repo → **Actions** 頁籤
2. 點左側「591 每日買賣物件蒐集」
3. 點「**Run workflow**」手動觸發
4. 查看執行 log 確認無錯誤
5. 去 Notion 確認資料是否出現 🎉

---

## ⏰ 執行時間

預設每天早上 **8:00 台灣時間**自動執行。

若要改時間，修改 `.github/workflows/daily-scrape.yml`：
```yaml
- cron: "0 0 * * *"   # UTC 00:00 = 台灣 08:00
- cron: "30 23 * * *" # UTC 23:30 = 台灣 07:30
- cron: "0 22 * * *"  # UTC 22:00 = 台灣 06:00
```
> Cron 時間為 UTC，台灣時間需 -8 小時換算。

---

## 📊 Notion 資料庫建議視圖

建立以下幾個 View 方便使用：

| View 名稱 | 類型 | 篩選條件 |
|---|---|---|
| 📥 今日新案 | Table | 蒐集日期 = 今天 |
| ✅ 已聯繫 | Table | 狀態 = 已聯繫 |
| 💰 總覽（依價格） | Gallery | 依售價排序 |
| 🗺️ 依地區 | Board | 群組 = 地區 |

---

## ❓ 常見問題

**Q: 爬不到資料？**
A: 591 可能更新了 API，請回報或嘗試手動執行 `scraper.py` 看錯誤訊息。

**Q: Notion 寫入失敗 400 錯誤？**
A: 確認欄位名稱完全一致（包括括號和空格），且 Integration 已連接到資料庫。

**Q: 如何蒐集多個區域？**
A: 複製 `SEARCH_CONFIG` 並在 `main()` 中多次呼叫 `get_591_listings()`，每次帶入不同 config。
