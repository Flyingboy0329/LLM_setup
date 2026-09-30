import json
import secrets
from pathlib import Path
from typing import Dict, Any

SETTINGS_PATH = Path(__file__).resolve().parent.parent / "config" / "settings.json"

DEFAULT_SETTINGS = {
    "admin_secret_key": "",          # 本地管理員金鑰 (若為空自動隨機生成)
    "ngrok_authtoken": "",           # 使用者個人的 ngrok authtoken
    "ngrok_domain": "",              # 使用者專屬的固定 static domain
    "custom_context_length": 0,      # 0 代表直接採用系統「推薦大小」
    "enable_gpu_balance_for_gaming": True # 保障遊戲優先級防呆開關
}

def load_settings() -> Dict[str, Any]:
    """讀取設定檔，若不存在則自動初始化預設值"""
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not SETTINGS_PATH.exists():
        # 初次啟動自動隨機生成一組安全的 16 位金鑰
        initial_cfg = DEFAULT_SETTINGS.copy()
        initial_cfg["admin_secret_key"] = f"key_{secrets.token_hex(8)}"
        save_settings(initial_cfg)
        return initial_cfg

    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            # 補齊可能缺失的新欄位
            for k, v in DEFAULT_SETTINGS.items():
                if k not in cfg:
                    cfg[k] = v
            return cfg
    except Exception as e:
        print(f"[WARN] 讀取 settings.json 異常: {e}，使用預設值替代。")
        return DEFAULT_SETTINGS.copy()

def save_settings(new_settings: Dict[str, Any]) -> bool:
    """保存或更新設定檔，供 UI 或終端機調用"""
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(new_settings, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[ERR] 保存 settings.json 失敗: {e}")
        return False

def update_admin_key(new_key: str) -> bool:
    """更新管理員金鑰的便捷接口"""
    cfg = load_settings()
    cfg["admin_secret_key"] = new_key.strip()
    return save_settings(cfg)