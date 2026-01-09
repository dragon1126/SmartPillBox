
# AIoT Smart Pill Box (智慧聯網藥盒) 

這是一個基於 **ESP32** 與 **Google Ecosystem (Apps Script + Sheets)** 的智慧藥盒專案。
它解決了傳統藥盒「設定麻煩」與「容易忘記」的痛點，透過 LINE 即可用**自然語言**設定鬧鐘，並具備**開蓋自動偵測**功能，實現真正的智慧化用藥管理。

##  主要功能 (Key Features)

###  1. 雙向 LINE 整合

* **自然語言設定**：直接對 LINE 機器人說「每天早上9點半吃藥」或「每週一三五 20:00 提醒」，系統自動解析並同步。
* **即時推播**：
*  **時間到**：手機收到吃藥提醒。
*  **已服用**：按下按鈕或打開藥盒後，手機收到確認通知。



###  2. 智慧邏輯 (Smart Logic)

* **開蓋偵測**：內建微動開關，打開藥盒蓋子即視為「已吃藥」，自動停止鬧鐘並上傳紀錄。
* **防重複干擾**：若當日提早打開過藥盒（提早吃藥），鬧鐘時間到將**不再響鈴**，避免打擾。
* **每日重置**：跨日（00:00）自動重置吃藥狀態。

###  3. 雲端同步與紀錄

* **Google Sheets 後台**：所有設定（Alarm Config）與紀錄（Eat Logs）皆儲存在雲端試算表。
* **自動校時**：ESP32 開機自動透過 NTP 校正時間，精準度高。
* **斷電保護**：WiFi 設定與 UserID 存於本機，斷電重開機後自動連線同步。

---

##  硬體架構 (Hardware)

### 零件清單

* **MCU**: ESP32 Development Board (WROOM-32)
* **Display**: 0.96" SSD1306 OLED (I2C)
* **Input**: Rotary Encoder (EC11)
* **Output**: Passive Buzzer (被動蜂鳴器)
* **Sensor**: Micro Switch / Reed Switch x 2 (用於偵測藥盒開蓋)

###  接線圖 (Pinout)

| 模組 (Module) | 腳位 (Pin Name) | ESP32 GPIO | 備註 (Note) |
| --- | --- | --- | --- |
| **OLED** | SDA | **21** | I2C Data |
|  | SCL | **22** | I2C Clock |
|  | VCC | 3.3V |  |
| **Encoder** | CLK | **32** | 旋轉脈衝 |
|  | DT | **33** | 旋轉方向 |
|  | SW | **4** | 按鈕 (內建上拉) |
| **Buzzer** | Signal | **15** | 聲音輸出 |
| **Lid Switch 1** | Pin 1 | **18** | 開蓋偵測 (接地導通) |
| **Lid Switch 2** | Pin 1 | **19** | 開蓋偵測 (接地導通) |
| **GND** | Common GND | GND | 所有元件共地 |

> **注意**：藥盒開關 (Lid Switch) 採用接地觸發邏輯 (Active Low)。當開關導通 (接地) 時，視為「開蓋」。

---

##  安裝與部署 (Installation)

### Step 1: 雲端後端 (Google Apps Script)

1. 建立一個新的 [Google Sheet](https://sheets.google.com)。
2. 點擊 `擴充功能` > `Apps Script`。
3. 將本專案 `google_apps_script/Code.gs` 的內容複製貼上。
4. 填入您的：
* `CHANNEL_ACCESS_TOKEN` (來自 LINE Developers)
* `SHEET_ID` (Google Sheet 網址中的 ID)


5. **部署 (Deploy)**：
* 選擇 `網頁應用程式 (Web App)`。
* 執行身分：`我 (Me)`。
* 誰可以存取：`任何人 (Anyone)`。
* **複製產生的 Web App URL** (以 `.../exec` 結尾)。



### Step 2: LINE Bot 設定

1. 在 LINE Developers Console 中，開啟 `Messaging API`。
2. 將 Step 1 產生的 **Web App URL** 貼入 `Webhook URL` 欄位。
3. 開啟 `Use webhook`。

### Step 3: ESP32 韌體 (MicroPython)

1. 確保 ESP32 已燒錄 MicroPython 韌體。
2. 將以下檔案上傳至 ESP32 (使用 Thonny IDE)：
* `ssd1306py.py` (OLED 驅動庫)
* `main.py` (主程式)


3. 修改 `main.py` 中的設定：
```python
GAS_URL = "您的_WEB_APP_URL_填在這裡"

```


4. 執行程式，依照螢幕指示連接 WiFi 並綁定使用者。

---

##  使用說明 (User Guide)

### 1. 初次綁定

1. 手機對 LINE 機器人輸入 **「綁定」**。
2. 機器人回傳 6 位數代碼 (例如 `123456`)。
3. 在 ESP32 選單選擇 `Bind User`，輸入該代碼。
4. 螢幕顯示 `Bind Success` 即完成配對。

### 2. 設定鬧鐘 (自然語言)

直接在 LINE 輸入指令，例如：

* 「每天早上9點半吃藥」
* 「平日晚上8點提醒」
* 「每週一三五 12:00」
* 「提醒 10:30」 (預設每天)

> **同步方式**：設定完成後，ESP32 需重新開機或選擇 `Sync Cloud` 才會更新設定。

### 3. 吃藥與紀錄

* **時間到**：蜂鳴器響起，LINE 收到通知。
* **動作**：打開藥盒蓋子 (或按下旋鈕)。
* **結果**：鬧鐘停止，LINE 收到「已吃藥」確認，Google Sheet 新增一筆 Log。

---

##  專案結構

```
SmartPillBox/
├── README.md               # 本說明檔
├── esp32/                  # 裝置端程式碼
│   ├── main.py             # 主邏輯 (WiFi, OLED, 傳感器, API)
│   └── ssd1306py.py        # OLED 驅動
└── google_apps_script/     # 雲端端程式碼
    └── Code.gs             # 處理 LINE Webhook 與 資料庫邏輯

```



## 主UI結構

'''
SmartPillBox_UI_Architecture/
├── Device_Side_OLED (ESP32_FSM)/       # 裝置端介面 (有限狀態機)
│   ├── 1. Startup_Sequence/            # 開機流程
│   │   ├── WiFi_Scanning_View          # [SCAN_VIEW] 掃描周遭 WiFi
│   │   └── Password_Input_View         # [PASSWORD_INPUT] 旋轉輸入 WiFi 密碼
│   │
│   ├── 2. Main_Display (Idle)/         # 待機主畫面
│   │   └── Clock_View                  # [CLOCK_VIEW]
│   │       ├── Information             # 顯示：現在時間 / 鬧鐘時間 / 當日吃藥狀態[V][ ]
│   │       └── Interaction             # 動作：按下旋鈕 -> 進入選單
│   │
│   ├── 3. Menu_System/                 # 選單系統 [MENU_SELECT]
│   │   ├── Set_Time                    # -> 進入 [SET_HOUR] -> [SET_MINUTE]
│   │   ├── Set_Days                    # -> 進入 [SET_WEEKDAY] (開關特定星期)
│   │   ├── Sync_Cloud                  # -> 觸發 API (GET_CONFIG) 同步雲端設定
│   │   ├── Bind_User                   # -> 進入 [BIND_INPUT] 輸入 6 位綁定碼
│   │   ├── Log_Now                     # -> 觸發 API (EAT) 手動上傳紀錄
│   │   └── Back                        # -> 返回主畫面
│   │
│   └── 4. Alert_Mode/                  # 警報模式
│       └── Alarm_Ringing               # [ALARM_RINGING]
│           ├── Display                 # 顯示 "Time to Eat!" 閃爍
│           └── Exit_Trigger            # 動作：按下按鈕 或 打開藥盒 -> 停止並上傳
│
└── Mobile_Side_LINE (Chat_Interface)/  # 手機端介面 (LINE Bot)
    └── Conversational_UI/
        ├── Input_Commands/             # 使用者輸入指令
        │   ├── Setup_Alarm (NLP)       # 輸入 "每天9點吃藥" -> 解析並存入 Google Sheet
        │   ├── User_Binding            # 輸入 "綁定" -> 產生驗證碼
        │   └── Manual_Log              # 輸入 "吃藥" -> 雲端紀錄
        │
        └── Push_Notifications/         # 系統主動推播
            ├── Alarm_Alert             # "⏰ 時間到了！請記得吃藥"
            └── Action_Confirm          # "✅ 您已按下實體按鈕，紀錄成功"
            
'''

##  常見問題排除 (Troubleshooting)

* **ESP32 顯示 `API Error: 16**`
* 原因：連續請求太快，Socket 資源未釋放。
* 解法：程式已內建 `time.sleep(1)` 與 `gc.collect()` 機制，通常稍等一下即可恢復。


* **LINE 沒反應**
* 檢查 Google Apps Script 是否已部署為 **「新版本」 (New Version)**。
* 檢查 Webhook URL 是否正確且已啟用。


* **鬧鐘沒響**
* 檢查螢幕是否顯示 `[V]` (今日已吃)。如果是，這是正常的防干擾功能。重置 ESP32 可清除狀態。



---

##  License

此專案供學習與個人使用，歡迎 Fork 修改。
