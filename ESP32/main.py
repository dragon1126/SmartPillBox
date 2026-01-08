from machine import Pin, RTC, SoftI2C
import network
import time
import ssd1306py as lcd 
import ntptime 
import os
import json
import ujson
import urequests
import gc

# ==========================================
# 設定區 
# ==========================================
GAS_URL = "https://script.google.com/macros/s/AKfycbzKDhZvjdHClDMXHGdD0UG7sdhmKO4WHprAmV_RxHLzbpOQghF8KWyxhZrPOATL_euj/exec"
UTC_OFFSET = 8 * 3600 

# -----------------------------
# 1. 腳位
# -----------------------------
ROTARY_CLK_PIN = 32
ROTARY_DT_PIN = 33
ROTARY_SW_PIN = 4   
BUZZER_PIN = 15     
LID_PIN_1 = 18
LID_PIN_2 = 19

clk_pin = Pin(ROTARY_CLK_PIN, Pin.IN, Pin.PULL_UP)
dt_pin = Pin(ROTARY_DT_PIN, Pin.IN, Pin.PULL_UP)
sw_pin = Pin(ROTARY_SW_PIN, Pin.IN, Pin.PULL_UP)
buzzer = Pin(BUZZER_PIN, Pin.OUT)
buzzer.value(0)

# 藥盒開關 (上拉模式)
lid_switch_1 = Pin(LID_PIN_1, Pin.IN, Pin.PULL_UP)
lid_switch_2 = Pin(LID_PIN_2, Pin.IN, Pin.PULL_UP)

# -----------------------------
# 2. 變數
# -----------------------------
SCAN_VIEW = 0
PASSWORD_INPUT = 1
CLOCK_VIEW = 2 
MENU_SELECT = 3      
SET_HOUR = 4         
SET_MINUTE = 5       
SET_WEEKDAY = 6      
ALARM_RINGING = 7
BIND_INPUT = 8 

current_state = SCAN_VIEW
current_index = 0         
max_index = 0             

last_rotary_time = 0       
last_button_time = 0       
display_needs_update = True        
input_locked = False               

should_upload_log = False
should_bind_code = False
should_sync_config = False
should_notify_alarm = False

medication_taken_today = False
last_day_checked = -1

# 【新增】藥盒開關狀態旗標 (防止開著的時候一直觸發)
lid_triggered = False

PASSWORD_CHARS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ!@#$%^&*()_+-=[]{};:'\",.<>/?~`"
NUMERIC_CHARS = "0123456789" 
CONTROL_OPTIONS = ["OK", "DEL", "BACK"]

char_index = 0          
input_buffer = ""       
wifi_list = [] 
menu_index = 0
weekday_edit_index = 0 

WIFI_FILE = "wifi.txt"
ALARM_FILE = "alarm.json"
USER_ID_FILE = "user_id.txt"

alarm_config = {"hour": 8, "minute": 0, "days": [False]*7, "enabled": False}
MENU_ITEMS = ["Set Time", "Set Days", "Sync Cloud", "Bind User", "Log Now", "Back"]
WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# -----------------------------
# 3. OLED
# -----------------------------
try:
    i2c = SoftI2C(scl=Pin(22), sda=Pin(21))
    lcd.init_i2c(22, 21, 128, 64, i2c=i2c)
except:
    try: lcd.init_i2c(22, 21, 128, 64)
    except: pass

font16 = {0xe4bda0: [0x08], 0xe5a5bd: [0x10]} 
try: lcd.set_font(font16, 16)
except: pass
lcd.clear(); lcd.show()

# -----------------------------
# 4. 檔案與網路
# -----------------------------
def load_config():
    global alarm_config
    wifi_data = (None, None)
    if WIFI_FILE in os.listdir():
        try:
            with open(WIFI_FILE, "r") as f:
                lines = f.read().split("\n")
                if len(lines) >= 2: wifi_data = (lines[0].strip(), lines[1].strip())
        except: pass

    if ALARM_FILE in os.listdir():
        try:
            with open(ALARM_FILE, "r") as f: alarm_config = json.load(f)
        except: pass
    return wifi_data

def save_wifi(ssid, pwd):
    with open(WIFI_FILE, "w") as f: f.write(f"{ssid}\n{pwd}")

def save_alarm():
    with open(ALARM_FILE, "w") as f: json.dump(alarm_config, f)
    
def get_user_id():
    if USER_ID_FILE in os.listdir():
        try:
            with open(USER_ID_FILE, "r") as f: return f.read().strip()
        except: pass
    return None

def save_user_id(uid):
    print("儲存 User ID:", uid) 
    with open(USER_ID_FILE, "w") as f: f.write(uid)

def connect_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF); wlan.active(True)
    lcd.clear(); lcd.text("Connecting...", 0, 0, 8); lcd.show()
    wlan.disconnect()
    try: wlan.connect(ssid, password)
    except: return False
    max_wait = 15 
    while max_wait > 0:
        if wlan.isconnected(): return True
        time.sleep(1); max_wait -= 1
    return False

def sync_ntp_time():
    lcd.clear(); lcd.text("Syncing Time...", 0, 20, 8); lcd.show()
    try: ntptime.settime() 
    except: pass

def scan_wifi():
    global max_index, current_index
    lcd.clear(); lcd.text("Scanning...", 0, 20, 8); lcd.show()
    try: nets = network.WLAN(network.STA_IF).scan()
    except: nets = []
    new_list = []
    for ap in nets:
        try:
            ssid = ap[0].decode('utf-8')
            if ssid: new_list.append(f"{ssid} ({ap[3]}dBm)")
        except: continue 
    max_index = len(new_list); current_index = 0
    return new_list

def api_request(payload, max_retries=3):
    # 1. 組合網址
    params = ""
    for key in payload:
        params += "&" + key + "=" + str(payload[key])
    full_url = GAS_URL + "?device=esp32" + params
    
    # 2. 關鍵修正：加入 Connection: close 表頭
    # 這告訴 Google 伺服器：「回傳完資料請馬上掛斷，不要佔線」
    headers = {
        'Connection': 'close',
        'User-Agent': 'Mozilla/5.0' # 偽裝一下比較不會被擋
    }
    
    for attempt in range(max_retries):
        gc.collect() 
        
        if attempt > 0:
            print(f"等待資源釋放... ({attempt}/{max_retries})")
            time.sleep(2)
            
        print(f"發送請求...")
        res = None
        try:
            # 發送請求 (帶上 headers)
            res = urequests.get(full_url, headers=headers)
            print("狀態碼:", res.status_code)
            
            data = None
            try:
                data = res.json()
            except:
                print("JSON 解析失敗")
            
            # 關閉連線
            if res:
                res.close()
                del res # 強制刪除物件
            
            gc.collect() # 再次清理
            return data
                
        except OSError as e:
            print(f"連線錯誤: {e}")
            if res:
                try: res.close()
                except: pass
            
            # 如果是 Error 16，休息一下再試，通常 Connection: close 會解決它
            if "16" in str(e):
                time.sleep(1)
                
        except Exception as e:
            print(f"其他錯誤: {e}")
            if res:
                try: res.close()
                except: pass
            
    print("多次嘗試失敗，放棄。")
    return None
# -----------------------------
# 5. 邏輯處理
# -----------------------------
def perform_sync_config():
    global alarm_config
    uid = get_user_id()
    if not uid:
        lcd.clear(); lcd.text("No User Bound", 0, 20, 8); lcd.show(); time.sleep(2)
        return

    lcd.clear(); lcd.text("Syncing Config...", 0, 20, 8); lcd.show()
    resp = api_request({'action': 'get_config', 'userId': uid})
    
    lcd.clear()
    if resp and resp.get('status') == 'success':
        try:
            h = int(resp.get('hour'))
            m = int(resp.get('minute'))
            
            alarm_config['hour'] = h
            alarm_config['minute'] = m
            alarm_config['enabled'] = True 
            
            cloud_days = resp.get('days')
            if isinstance(cloud_days, list) and len(cloud_days) == 7:
                alarm_config['days'] = cloud_days
                
            save_alarm()
            
            lcd.text("Sync Success!", 0, 10, 8)
            lcd.text(f"Alarm: {h:02}:{m:02}", 0, 30, 8)
            
            active_days = ""
            for i in range(7):
                if alarm_config['days'][i]: active_days += str(i+1)
            if active_days == "": active_days = "None"
            lcd.text(f"Days: {active_days}", 0, 50, 8)
            
        except Exception as e:
            print("同步處理錯誤:", e)
            lcd.text("Data Error", 0, 20, 8)
    else:
        lcd.text("Sync Failed", 0, 20, 8)
    
    lcd.show(); time.sleep(2)

def handle_input(charset, is_wifi):
    global input_buffer, char_index, current_state, should_bind_code, should_sync_config
    
    clen = len(charset)
    if char_index < clen:
        input_buffer += charset[char_index]
        char_index = 0
    else:
        cmd = char_index - clen
        if cmd == 0: # OK
            if is_wifi: 
                ssid = wifi_list[current_index].split(' (')[0]
                if connect_wifi(ssid, input_buffer):
                    save_wifi(ssid, input_buffer)
                    sync_ntp_time()
                    should_sync_config = True
                    current_state = CLOCK_VIEW
                else: current_state = SCAN_VIEW
            else: 
                should_bind_code = True 
                current_state = CLOCK_VIEW
                
        elif cmd == 1: # DEL
            input_buffer = input_buffer[:-1]
        elif cmd == 2: # BACK
            if is_wifi: current_state = SCAN_VIEW
            else: current_state = MENU_SELECT

def perform_bind():
    global input_buffer
    lcd.clear(); lcd.text("Binding...", 0, 20, 8); lcd.show()
    resp = api_request({'action': 'bind', 'code': input_buffer})
    lcd.clear()
    if resp and resp.get('status') == 'success':
        uid = resp.get('userId')
        save_user_id(uid)
        lcd.text("Bind Success!", 0, 20, 8)
    else:
        lcd.text("Bind Failed!", 0, 20, 8)
    lcd.show(); time.sleep(2)

def upload_log():
    uid = get_user_id()
    if not uid:
        lcd.clear(); lcd.text("Please Bind 1st", 0, 20, 8); lcd.show(); time.sleep(2)
        return
    lcd.clear(); lcd.text("Uploading...", 0, 20, 8); lcd.show()
    resp = api_request({'action': 'eat', 'userId': uid})
    lcd.clear()
    if resp: lcd.text("Log Saved!", 0, 20, 8)
    else: lcd.text("Upload Failed", 0, 20, 8)
    lcd.show(); time.sleep(1)

def notify_alarm():
    uid = get_user_id()
    if not uid: return
    print("通知 LINE: 鬧鐘響了")
    api_request({'action': 'notify_alarm', 'userId': uid})

# -----------------------------
# 6. 中斷與開關檢測
# -----------------------------
def rotary_handler(pin):
    global current_index, max_index, display_needs_update, char_index, current_state
    global menu_index, alarm_config, weekday_edit_index, last_rotary_time
    
    if time.ticks_diff(time.ticks_ms(), last_rotary_time) < 5: return
    last_rotary_time = time.ticks_ms()

    if clk_pin.value() == 0:
        dt_val = dt_pin.value()
        direction = -1 if dt_val == 1 else 1
            
        if current_state == SCAN_VIEW and max_index > 0:
            current_index = (current_index + direction) % max_index
        elif current_state == PASSWORD_INPUT:
            total_opts = len(PASSWORD_CHARS) + 3
            char_index = (char_index + direction + total_opts) % total_opts
        elif current_state == BIND_INPUT: 
            total_opts = len(NUMERIC_CHARS) + 3
            char_index = (char_index + direction + total_opts) % total_opts
        elif current_state == MENU_SELECT:
            menu_index = (menu_index + direction) % len(MENU_ITEMS)
        elif current_state == SET_HOUR:
            alarm_config["hour"] = (alarm_config["hour"] + direction) % 24
        elif current_state == SET_MINUTE:
            alarm_config["minute"] = (alarm_config["minute"] + direction) % 60
        elif current_state == SET_WEEKDAY:
            weekday_edit_index = (weekday_edit_index + direction) % 8
        display_needs_update = True

def button_handler(pin):
    global current_state, input_locked, display_needs_update
    global input_buffer, char_index, current_index, wifi_list
    global last_button_time, menu_index, alarm_config, should_upload_log, should_bind_code, should_sync_config
    global weekday_edit_index, medication_taken_today
    
    if input_locked: return
    if time.ticks_diff(time.ticks_ms(), last_button_time) < 250: return
    input_locked = True; time.sleep_ms(20) 
    
    if pin.value() == 0:
        last_button_time = time.ticks_ms()
        
        if current_state == SCAN_VIEW and max_index > 0:
            input_buffer = ""; char_index = 0; current_state = PASSWORD_INPUT
        elif current_state == PASSWORD_INPUT:
            handle_input(PASSWORD_CHARS, is_wifi=True)
        elif current_state == BIND_INPUT:
            handle_input(NUMERIC_CHARS, is_wifi=False)
        elif current_state == CLOCK_VIEW:
            menu_index = 0; current_state = MENU_SELECT
        elif current_state == MENU_SELECT:
            item = MENU_ITEMS[menu_index]
            if item == "Set Time": current_state = SET_HOUR
            elif item == "Set Days": weekday_edit_index = 0; current_state = SET_WEEKDAY
            elif item == "Sync Cloud": 
                current_state = CLOCK_VIEW; should_sync_config = True
            elif item == "Bind User": 
                current_state = BIND_INPUT; input_buffer = ""; char_index = 0
            elif item == "Log Now": 
                current_state = CLOCK_VIEW; should_upload_log = True
                medication_taken_today = True 
            elif item == "Back": current_state = CLOCK_VIEW
        elif current_state == SET_HOUR: current_state = SET_MINUTE
        elif current_state == SET_MINUTE:
            alarm_config["enabled"] = True; save_alarm(); current_state = CLOCK_VIEW
        elif current_state == SET_WEEKDAY:
            if weekday_edit_index < 7: alarm_config["days"][weekday_edit_index] = not alarm_config["days"][weekday_edit_index]
            else: save_alarm(); current_state = CLOCK_VIEW
        elif current_state == ALARM_RINGING:
            buzzer.value(0); current_state = CLOCK_VIEW; should_upload_log = True
            medication_taken_today = True

        display_needs_update = True
    input_locked = False 

# 輪詢方式檢測藥盒開關
def check_lid_status_polling():
    global lid_triggered, current_state, should_upload_log, medication_taken_today
    
    # 檢查是否有任何一個開關被觸發 (低電位)
    is_lid_open = (lid_switch_1.value() == 0) or (lid_switch_2.value() == 0)
    
    if is_lid_open:
        # 如果還沒被標記為觸發狀態 (避免一直重複觸發)
        if not lid_triggered:
            print("偵測到開蓋... 等待確認")
            # 延遲 0.5 秒 (500ms) 進行確認
            time.sleep_ms(500)
            
            # 再次檢查
            if (lid_switch_1.value() == 0) or (lid_switch_2.value() == 0):
                print("確認開蓋！執行動作")
                lid_triggered = True  # 標記為已觸發
                
                # 執行吃藥動作
                if current_state == ALARM_RINGING:
                    buzzer.value(0)
                    current_state = CLOCK_VIEW
                    should_upload_log = True
                    medication_taken_today = True
                elif current_state == CLOCK_VIEW:
                    should_upload_log = True
                    medication_taken_today = True
    else:
        # 如果蓋子關上了 (High)，重置觸發旗標，允許下次觸發
        if lid_triggered:
            print("藥盒已關閉")
            lid_triggered = False

# 綁定中斷 (只綁旋鈕和按鍵，不綁藥盒)
clk_pin.irq(trigger=Pin.IRQ_FALLING, handler=rotary_handler)
sw_pin.irq(trigger=Pin.IRQ_FALLING, handler=button_handler)

# -----------------------------
# 7. UI
# -----------------------------
def draw_input_ui(title, charset):
    global input_buffer, char_index
    lcd.clear()
    lcd.text(title, 0, 0, 8)
    lcd.text(input_buffer[-13:], 0, 16, 8) 
    mid = 2; start = char_index - mid
    total = len(charset) + 3
    for i in range(5):
        idx = (start + i) % total
        txt = ""
        if idx < len(charset): txt = charset[idx]
        else: txt = CONTROL_OPTIONS[idx - len(charset)]
        if txt == "DEL": txt = "<-"
        elif txt == "BACK": txt = "RT"
        x = 10 + i * 24
        lcd.text(txt, x, 40, 8)
        if i == mid: lcd.text("^", x + (4 if len(txt)>1 else 0), 52, 8)
    lcd.show()

def update_ui():
    if current_state == SCAN_VIEW:
        if wifi_list: lcd.clear(); lcd.text(wifi_list[current_index][:16], 0, 0, 8); lcd.show()
    elif current_state == PASSWORD_INPUT: draw_input_ui("Enter WiFi Pass", PASSWORD_CHARS)
    elif current_state == BIND_INPUT: draw_input_ui("Enter Bind Code", NUMERIC_CHARS)
    elif current_state == MENU_SELECT:
        lcd.clear(); lcd.text("--- Menu ---", 0, 0, 8)
        for i, item in enumerate(MENU_ITEMS):
            pre = "> " if i == menu_index else "  "
            lcd.text(f"{pre}{item}", 0, 16 + i*10, 8)
        lcd.show()
    elif current_state == SET_HOUR:
        lcd.clear(); lcd.text("Set Hour", 0, 0, 8)
        lcd.text(f"{alarm_config['hour']:02}", 50, 30, 8); lcd.show()
    elif current_state == SET_MINUTE:
        lcd.clear(); lcd.text("Set Minute", 0, 0, 8)
        lcd.text(f"{alarm_config['minute']:02}", 50, 30, 8); lcd.show()
    elif current_state == SET_WEEKDAY:
        lcd.clear(); lcd.text("Set Days", 0, 0, 8)
        idx = weekday_edit_index
        if idx < 7:
            day = WEEKDAY_NAMES[idx]
            status = "ON" if alarm_config['days'][idx] else "OFF"
            lcd.text(f"{day}: {status}", 30, 30, 8)
        else: lcd.text("Save & Exit", 20, 30, 8)
        lcd.show()

# -----------------------------
# 8. 鬧鐘檢查
# -----------------------------
last_minute_checked = -1
def check_alarm():
    global current_state, last_minute_checked, should_notify_alarm, medication_taken_today
    if not alarm_config["enabled"]: return
    
    t = time.localtime(time.time() + UTC_OFFSET)
    wday, hour, minute = t[6], t[3], t[4]
    
    if minute == last_minute_checked: return
    last_minute_checked = minute
    
    if hour == alarm_config["hour"] and minute == alarm_config["minute"]:
        if alarm_config["days"][wday] and not medication_taken_today:
            current_state = ALARM_RINGING
            print("鬧鐘響了！")
            should_notify_alarm = True 

# -----------------------------
# 9. 主程式
# -----------------------------
gc.enable()
saved_ssid, saved_pass = load_config()
wlan = network.WLAN(network.STA_IF); wlan.active(True)

if saved_ssid and saved_pass:
    if connect_wifi(saved_ssid, saved_pass):
        sync_ntp_time()
        should_sync_config = True 
        current_state = CLOCK_VIEW
    else: wifi_list = scan_wifi(); current_state = SCAN_VIEW
else: wifi_list = scan_wifi(); current_state = SCAN_VIEW

last_clock_update = 0
alarm_toggle_flag = False

while True:
    # 每次迴圈都檢查藥盒開關
    check_lid_status_polling()

    if should_bind_code:
        perform_bind(); should_bind_code = False; display_needs_update = True
    if should_upload_log:
        upload_log(); should_upload_log = False; display_needs_update = True
    if should_sync_config:
        perform_sync_config(); should_sync_config = False; display_needs_update = True
    if should_notify_alarm:
        notify_alarm(); should_notify_alarm = False 

    if current_state == CLOCK_VIEW:
        check_alarm()
        now = time.ticks_ms()
        if time.ticks_diff(now, last_clock_update) > 1000:
            t = time.localtime(time.time() + UTC_OFFSET)
            
            if last_day_checked != t[2]:
                medication_taken_today = False
                last_day_checked = t[2]
                print("日期變更，重置吃藥狀態")

            lcd.clear()
            lcd.text(f"{t[3]:02}:{t[4]:02}:{t[5]:02}", 30, 20, 8)
            status_text = "Bound" if get_user_id() else "Unbound"
            
            if alarm_config['enabled']:
                alarm_time = f"{alarm_config['hour']:02}:{alarm_config['minute']:02}"
                taken_mark = "[V]" if medication_taken_today else "[ ]"
                lcd.text(f"Alarm: {alarm_time} {taken_mark}", 0, 40, 8)
            else:
                lcd.text("Alarm: OFF", 0, 40, 8)
                
            lcd.show()
            last_clock_update = now
            
    elif current_state == ALARM_RINGING:
         now = time.ticks_ms()
         if time.ticks_diff(now, last_clock_update) > 500:
             alarm_toggle_flag = not alarm_toggle_flag
             if alarm_toggle_flag:
                 lcd.clear(); lcd.text("Time to Eat!", 20, 30, 8); lcd.show(); buzzer.value(1)
             else:
                 lcd.clear(); lcd.show(); buzzer.value(0)
             last_clock_update = now

    if display_needs_update:
        update_ui()
        display_needs_update = False
        
    time.sleep_ms(20)


