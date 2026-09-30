import os
import sys
import json
import webbrowser
from pathlib import Path

SETTINGS_FILE = Path(__file__).resolve().parent.parent / "config" / "settings.json"

def display_security_notice():
    """IE 風險控管：聊天紀錄與公網暴露資訊安全宣告"""
    notice = """
╔══════════════════════════════════════════════════════════════════════════════╗
║                    ⚠️  資安防線與個人隱私安全宣告                           ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ 1. 【公網暴露風險】：                                                        ║
║    啟用 ngrok 外網穿透後，任何取得該 URL 的使用者皆可直接對您的本機發送請求。 ║
║ 2. 【對話紀錄存取警示】：                                                    ║
║    請注意！所有透過公網網址傳輸的資料都會經由外部節點轉發，且若您的本地 Agent ║
║    有掛載硬碟讀寫或系統工具，可能導致本地檔案被外網訪客調閱！                 ║
║ 3. 【防護最佳實踐】：                                                        ║
║    - 嚴禁在對話中輸入個人帳號密碼、信用卡號、私鑰或公司敏感代碼。             ║
║    - 建議前往 ngrok 儀表板啟用 Basic Auth (帳號密碼驗證) 進行二次阻截。       ║
╚══════════════════════════════════════════════════════════════════════════════╝
    """
    print(notice)

def setup_ngrok_wizard() -> dict:
    """引導使用者註冊並設定專屬網域"""
    config = {}
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {}

    authtoken = config.get("ngrok_authtoken", "")
    domain = config.get("ngrok_domain", "")

    if not authtoken:
        print("\n[ngrok 引導精靈]")
        print("💡 每個 ngrok 帳號均享有『1 個免費永久固定自訂網域 (Static Domain)』！")
        print("💡 請至 https://dashboard.ngrok.com 註冊並複製您的 Authtoken 與 Domain。\n")
        
        choice = input("是否自動開啟 ngrok 儀表板註冊網頁？ (y/n): ").strip().lower()
        if choice == 'y':
            webbrowser.open("https://dashboard.ngrok.com/get-started/your-authtoken")

        authtoken = input("請貼上您的 ngrok Authtoken: ").strip()
        domain = input("請貼上您的專屬 Static Domain (若無請直接按 Enter 跳過): ").strip()

        config["ngrok_authtoken"] = authtoken
        config["ngrok_domain"] = domain
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        print("✅ 設定已妥善保存至 config/settings.json\n")

    return config

def start_ngrok_tunnel(port: int = 8080):
    """啟動安全穿透隧道"""
    display_security_notice()
    config = setup_ngrok_wizard()

    try:
        from pyngrok import ngrok, conf
        if config.get("ngrok_authtoken"):
            ngrok.set_auth_token(config["ngrok_authtoken"])

        tunnel_options = {"addr": port, "proto": "http"}
        if config.get("ngrok_domain"):
            tunnel_options["domain"] = config["ngrok_domain"]

        print(f"[*] 正在建立安全連線至本地 Port {port}...")
        public_url = ngrok.connect(**tunnel_options)
        print("=" * 60)
        print(f"🎉 【穿透成功】您的專屬公網存取節點已建立：")
        print(f"👉 存取網址: {public_url}")
        print("=" * 60)
        return public_url
    except Exception as e:
        print(f"❌ ngrok 啟動失敗: {e}")
        return None

if __name__ == "__main__":
    start_ngrok_tunnel(8080)