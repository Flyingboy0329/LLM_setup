import os
import sys
from pathlib import Path
from typing import Optional
from duckduckgo_search import DDGS
from mcp.server.fastmcp import FastMCP
import yfinance as yf
import pandas as pd

# 引入設定管理中樞
from core.config_manager import load_settings

# 初始化 FastMCP 服務
mcp = FastMCP("llm-setup-tools")
WORKSPACE_DIR = Path(__file__).resolve().parent.parent

def _get_current_admin_key() -> str:
    """動態取得當前最新設定的管理員金鑰"""
    cfg = load_settings()
    return cfg.get("admin_secret_key", "llm_secure_key_2026")

def _verify_sandbox_path(relative_path: str) -> Optional[Path]:
    """IE 防呆機制：確保路徑嚴格限制在專案沙盒內"""
    clean_path = relative_path.replace("\\", "/").strip().lstrip("/")
    target_path = (WORKSPACE_DIR / clean_path).resolve()
    if not str(target_path).startswith(str(WORKSPACE_DIR)):
        return None
    return target_path

# ==================== 本地專案檔案管理工具 ====================

@mcp.tool()
def read_project_file(relative_path: str, secret_key: str = "") -> str:
    """【專案讀檔工具】讀取專案內指定文字或代碼檔案。"""
    safe_path = _verify_sandbox_path(relative_path)
    if not safe_path:
        return "❌ 錯誤：路徑超出 LLM_setup 沙盒範圍！"
    if not safe_path.exists():
        return f"❌ 檔案不存在: {relative_path}"

    current_admin_key = _get_current_admin_key()
    if "config" in str(safe_path) and secret_key != current_admin_key:
        return "⚠️ 【拒絕存取】：存取核心設定檔必須提供正確的管理員金鑰 (secret_key)！"

    try:
        with open(safe_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            return f"📄 【讀取成功: {relative_path}，總行數: {len(lines)} 行】\n" + "".join(lines)
    except Exception as e:
        return f"❌ 讀取失敗: {str(e)}"

@mcp.tool()
def write_project_file(relative_path: str, content: str, secret_key: str) -> str:
    """【專案寫檔工具】在專案內建立或更新檔案。必須提供管理員 secret_key。"""
    current_admin_key = _get_current_admin_key()
    if secret_key != current_admin_key:
        return "⚠️ 【拒絕存取】：未提供或金鑰錯誤，嚴禁寫入本地磁碟！"

    safe_path = _verify_sandbox_path(relative_path)
    if not safe_path:
        return "❌ 錯誤：路徑超出沙盒邊界！"

    try:
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        with open(safe_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"✅ 成功寫入檔案: {relative_path} (位元組: {len(content)})"
    except Exception as e:
        return f"❌ 寫入失敗: {str(e)}"

# （下方 list_project_structure, web_search, get_taiwan_stock 等工具維持不變）