import os
import sys
import psutil
import subprocess
from pathlib import Path
from core.hardware import get_nvidia_gpus, calculate_hardware_plan

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "Models"

# 就地尋找執行檔：優先搜尋當前專案根目錄與 LLM 子資料夾
LLAMA_EXE_CANDIDATES = [
    PROJECT_ROOT / "llama-server.exe",
    PROJECT_ROOT / "LLM" / "llama-server.exe",
    PROJECT_ROOT / "bin" / "llama-server.exe"
]

def find_llama_server() -> str:
    for candidate in LLAMA_EXE_CANDIDATES:
        if candidate.exists():
            return str(candidate)
    return "llama-server.exe"

def scan_available_models():
    """列出 Models 資料夾下所有 GGUF 模型"""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    return list(MODELS_DIR.glob("*.gguf"))

# ... (其餘 start_llama_engine 邏輯維持不變)

def start_llama_engine(model_filename: str = None, custom_ctx: int = None, port: int = 8080):
    models = scan_available_models()
    if not models:
        print(f"⚠️ [防呆警告] 在 {MODELS_DIR} 找不到任何 .gguf 模型！")
        print("💡 提示：請至 Discord 討論串 HuggingFace 連結下載後丟入 Models 資料夾。")
        return None

    # 如果沒指定，預設載入清單中的第一個模型
    selected_model = models[0] if not model_filename else MODELS_DIR / model_filename
    if not selected_model.exists():
        print(f"❌ 指定模型不存在: {selected_model}")
        return None

    # 硬體推論調度分析
    gpus = get_nvidia_gpus()
    plan = calculate_hardware_plan(gpus, custom_ctx=custom_ctx)

    exe_path = find_llama_server()
    cmd = [
        exe_path,
        "-m", str(selected_model),
        "-c", str(plan["ctx"]),
        "-ngl", str(plan["ngl"]),
        "--port", str(port),
        "--host", "0.0.0.0",
        "-fa"  # Flash Attention 節省顯存
    ]

    if plan["tensor_split"]:
        cmd.extend(["-ts", plan["tensor_split"]])

    print("=" * 60)
    print(f"🚀 [啟動引擎] 方案模式: {plan['tier']}")
    print(f"📦 載入模型: {selected_model.name}")
    print(f"🧠 上下文大小 (Context): {plan['ctx']} tokens")
    if plan["tensor_split"]:
        print(f"⚡ 雙卡切片參數: -ts {plan['tensor_split']}")
    print(f"🛠️ 完整執行指令: {' '.join(cmd)}")
    print("=" * 60)

    # 啟動子進程並實施遊戲優先權調度
    process = subprocess.Popen(cmd)

    # Windows 環境：降為背景優先權，杜絕搶佔 Riot 遊戲算力
    if sys.platform == "win32":
        try:
            p = psutil.Process(process.pid)
            p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
            print("🛡️ [IE 防呆] 已將 llama-server 調度為背景低優先級，Riot Vanguard 與遊戲運作不受影響。")
        except Exception as e:
            print(f"[WARN] 調整優先權失敗: {e}")

    return process

if __name__ == "__main__":
    start_llama_engine()