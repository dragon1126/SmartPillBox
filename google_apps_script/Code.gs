var CHANNEL_ACCESS_TOKEN = 'LINE的API'; 
var SHEET_ID = 'google試算表的網址'; 

// ==========================================
// 1. doGet (ESP32 讀取用)
// ==========================================
function doGet(e) {
  if (!e || !e.parameter) return ContentService.createTextOutput("No Params");
  var action = e.parameter.action;
  
  if (action === 'bind') {
    var result = verifyCode(e.parameter.code);
    return responseJSON(result.status === 'success' ? { 'status': 'success', 'userId': result.userId } : { 'status': 'error', 'message': result.message });
  }
  
  else if (action === 'eat') {
    var userId = e.parameter.userId;
    if (userId) {
      logAction(userId, "ESP32按鈕(GET)");
      pushMessageToUser(userId, "✅ 您已按下實體按鈕，吃藥紀錄成功！");
      return responseJSON({ 'status': 'success' });
    }
  }

  else if (action === 'get_config') {
    var userId = e.parameter.userId;
    var config = getUserConfig(userId); 
    if (config) {
      return responseJSON({ 'status': 'success', 'hour': config.hour, 'minute': config.minute, 'enabled': true, 'days': config.days });
    } else {
      return responseJSON({ 'status': 'success', 'hour': 8, 'minute': 0, 'enabled': false, 'days': [false,false,false,false,false,false,false] });
    }
  }

  else if (action === 'notify_alarm') {
     var userId = e.parameter.userId;
     if (userId) {
       pushMessageToUser(userId, "⏰ 時間到了！請記得吃藥 💊\n(若已服藥，請打開藥盒蓋子或按下按鈕)");
       return responseJSON({ 'status': 'success' });
     }
  }
  return ContentService.createTextOutput("GAS Online");
}

// ==========================================
// 2. doPost (LINE 寫入用)
// ==========================================
function doPost(e) {
  var msg = JSON.parse(e.postData.contents);
  if (msg.events) { 
    var event = msg.events[0];
    if (event.type === 'message') {
      var userId = event.source.userId;
      var text = event.message.text;
      
      if (text === '綁定') {
        var code = generateCode(userId);
        replyLine(event.replyToken, "🔗 綁定碼 (5分鐘有效)：\n" + code);
      } 
      else if(text.includes('吃藥') || text.includes('已吃藥')){
         logAction(userId, "手動紀錄(LINE)");
         replyLine(event.replyToken, "💊 收到！已手動紀錄吃藥時間。");
      }
      else {
         var result = parseNaturalLanguage(text);
         if (result.isValid) {
           saveUserConfig(userId, result.hour, result.minute, result.days);
           var dayStr = getDayString(result.days);
           replyLine(event.replyToken, "✅ 設定成功！\n⏰ 時間：" + pad(result.hour) + ":" + pad(result.minute) + "\n📅 頻率：" + dayStr + "\n\n(請記得按 ESP32 的 Sync Cloud 同步)");
         } else {
           if (text.includes("點") || text.includes("時") || text.includes(":")) {
             replyLine(event.replyToken, "🤔 我聽不太懂時間，請試著說：\n「每天早上9點吃藥」\n「每週一三五晚上8點半」");
           }
         }
      }
    }
  }
  return ContentService.createTextOutput("OK");
}

// ==========================================
// 3. 儲存與讀取 
// ==========================================
function saveUserConfig(userId, h, m, daysConfig) {
  var sheet = SpreadsheetApp.openById(SHEET_ID).getSheetByName('Users');
  var data = sheet.getDataRange().getValues();
  var rowIndex = -1;
  
  if (data[0].length < 6) { 
    sheet.getRange(1, 4).setValue("AlarmHour"); 
    sheet.getRange(1, 5).setValue("AlarmMinute"); 
    sheet.getRange(1, 6).setValue("AlarmDays"); 
  }

  for (var i = 1; i < data.length; i++) {
    if (data[i][0] == userId) {
      rowIndex = i + 1;
      break;
    }
  }

  if (rowIndex == -1) {
    sheet.appendRow([userId, 'User', new Date(), '', '', '']);
    rowIndex = sheet.getLastRow();
  }

  // 強制設定格式為整數 "0"，避免 Google 雞婆轉成時間格式
  sheet.getRange(rowIndex, 4).setNumberFormat("0").setValue(h);
  sheet.getRange(rowIndex, 5).setNumberFormat("0").setValue(m);
  sheet.getRange(rowIndex, 6).setValue(JSON.stringify(daysConfig)); 
}

function getUserConfig(userId) {
  var sheet = SpreadsheetApp.openById(SHEET_ID).getSheetByName('Users');
  var data = sheet.getDataRange().getValues();
  
  for (var i = 1; i < data.length; i++) {
    if (data[i][0] == userId) {
      var hour = parseInt(data[i][3]);
      var minute = parseInt(data[i][4]);
      
      if (isNaN(hour)) hour = 0;
      if (isNaN(minute)) minute = 0;

      var daysStr = data[i][5];
      var days = [false,false,false,false,false,false,false];
      try { if(daysStr) days = JSON.parse(daysStr); } catch(e){}

      return { hour: hour, minute: minute, days: days };
    }
  }
  return null;
}

// ==========================================
// 4. 其他輔助函式
// ==========================================
function parseNaturalLanguage(text) {
  var days = [false, false, false, false, false, false, false]; 
  var hour = -1; var minute = 0; var isValid = false;

  if (text.includes("每天") || text.includes("每日")) days = [true,true,true,true,true,true,true];
  else if (text.includes("平日")) days = [true,true,true,true,true,false,false];
  else if (text.includes("週末") || text.includes("假日")) days = [false,false,false,false,false,true,true];
  else {
    var hasSpecificDay = false;
    if (text.includes("一") || text.includes("1")) { days[0]=true; hasSpecificDay=true; }
    if (text.includes("二") || text.includes("2")) { days[1]=true; hasSpecificDay=true; }
    if (text.includes("三") || text.includes("3")) { days[2]=true; hasSpecificDay=true; }
    if (text.includes("四") || text.includes("4")) { days[3]=true; hasSpecificDay=true; }
    if (text.includes("五") || text.includes("5")) { days[4]=true; hasSpecificDay=true; }
    if (text.includes("六") || text.includes("6")) { days[5]=true; hasSpecificDay=true; }
    if (text.includes("日") || text.includes("7") || text.includes("天")) { days[6]=true; hasSpecificDay=true; }
    if (!hasSpecificDay) days = [true,true,true,true,true,true,true];
  }

  var timeMatch = text.match(/(\d{1,2})[:：點時]/);
  if (timeMatch) { hour = parseInt(timeMatch[1]); isValid = true; }
  
  if (isValid) {
    if (text.includes("下午") || text.includes("晚上") || text.includes("晚間") || text.includes("PM") || text.includes("pm")) {
      if (hour < 12) hour += 12;
    }
    if ((text.includes("中午") || text.includes("下午")) && hour == 12) hour = 12;
  }

  if (text.includes("半")) minute = 30;
  else {
    var minMatch = text.match(/[:：點時](\d{1,2})/);
    if (minMatch) minute = parseInt(minMatch[1]);
  }

  if (hour >= 24) hour = 0; if (minute >= 60) minute = 0;
  return { isValid: isValid, hour: hour, minute: minute, days: days };
}

function responseJSON(data) {
  return ContentService.createTextOutput(JSON.stringify(data)).setMimeType(ContentService.MimeType.JSON);
}
function pad(n) { return n < 10 ? '0' + n : n; }
function getDayString(days) {
  var allTrue = true; var allFalse = true; var str = ""; var names = ["一","二","三","四","五","六","日"];
  for(var i=0; i<7; i++) { if(!days[i]) allTrue = false; else { allFalse = false; str += names[i] + " "; } }
  if (allTrue) return "每天"; if (allFalse) return "未設定"; return "星期 " + str;
}
function generateCode(userId) {
  var code = Math.floor(100000 + Math.random() * 900000).toString();
  var sheet = SpreadsheetApp.openById(SHEET_ID).getSheetByName('Codes');
  var expireTime = new Date().getTime() + 5*60*1000; 
  sheet.appendRow([code, userId, expireTime, "WAIT"]); 
  return code;
}
function verifyCode(inputCode) {
  var sheet = SpreadsheetApp.openById(SHEET_ID).getSheetByName('Codes');
  var data = sheet.getDataRange().getValues();
  var now = new Date().getTime();
  for (var i = data.length - 1; i >= 0; i--) {
    if (data[i][0].toString() === inputCode.toString()) {
      if (data[i][3] === "USED") return { status: 'error', message: 'Code already used' };
      if (now > data[i][2]) return { status: 'error', message: 'Code expired' };
      sheet.getRange(i + 1, 4).setValue("USED");
      return { status: 'success', userId: data[i][1] };
    }
  }
  return { status: 'error', message: 'Code not found' };
}
function logAction(userId, note) {
  var sheet = SpreadsheetApp.openById(SHEET_ID).getSheetByName('Logs');
  sheet.appendRow([new Date(), userId, 'Eat', note]);
}
function replyLine(replyToken, text) {
  UrlFetchApp.fetch('https://api.line.me/v2/bot/message/reply', {
    'headers': { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + CHANNEL_ACCESS_TOKEN },
    'method': 'post',
    'payload': JSON.stringify({ 'replyToken': replyToken, 'messages': [{'type': 'text', 'text': text}] })
  });
}
function pushMessageToUser(userId, text) {
  try {
    UrlFetchApp.fetch('https://api.line.me/v2/bot/message/push', {
      'headers': { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + CHANNEL_ACCESS_TOKEN },
      'method': 'post',
      'payload': JSON.stringify({ 'to': userId, 'messages': [{'type': 'text', 'text': text}] })
    });
  } catch(e) {}
}