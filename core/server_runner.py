import os
import sys
import psutil
import subprocess
from pathlib import Path
from core.hardware import get_nvidia_gpus, calculate_hardware_plan

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "Models"

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

def start_llama_engine(
    model_filename: str = None, 
    custom_ctx: int = None, 
    port: int = 8080,
    enable_reasoning: bool = False,
    game_mode_background: bool = False
):
    models = scan_available_models()
    if not models:
        print(f"⚠️ [防呆警告] 在 {MODELS_DIR} 找不到任何 .gguf 模型！")
        print("💡 提示：請至 Discord 討論串 HuggingFace 連結下載後丟入 Models 資料夾。")
        return None

    # 模型精確命中校驗
    if model_filename:
        selected_model = Path(model_filename)
        if not selected_model.is_absolute():
            selected_model = MODELS_DIR / model_filename
    else:
        selected_model = models[0]

    if not selected_model.exists():
        print(f"❌ 指定模型不存在: {selected_model}")
        return None

    # 計算模型檔案大小以推薦最佳 Context
    try:
        model_size_gb = round(selected_model.stat().st_size / (1024 ** 3), 2)
    except Exception:
        model_size_gb = 0.0

    # 硬體推論調度分析
    gpus = get_nvidia_gpus()
    plan = calculate_hardware_plan(gpus, custom_ctx=custom_ctx, model_size_gb=model_size_gb)

    exe_path = find_llama_server()
    cmd = [
        exe_path,
        "-m", str(selected_model),
        "-c", str(plan["ctx"]),
        "-ngl", str(plan["ngl"]),
        "--port", str(port),
        "--host", "0.0.0.0",
        "-fa", "on",
        "--cache-type-k", "q8_0",
        "--cache-type-v", "q8_0"
    ]

    # 思維鏈開關
    if not enable_reasoning:
        cmd.append("--no-reasoning-preserve")

    # 雙卡張量切片
    if plan["tensor_split"]:
        cmd.extend(["-ts", plan["tensor_split"]])

    print("=" * 60)
    print(f"🚀 [啟動引擎] 方案模式: {plan['tier']}")
    print(f"📦 載入模型: {selected_model.name} ({model_size_gb} GB)")
    print(f"🧠 上下文大小 (Context): {plan['ctx']} tokens")
    if plan["tensor_split"]:
        print(f"⚡ 雙卡切片參數: -ts {plan['tensor_split']}")
    print(f"🛠️ 完整執行指令: {' '.join(cmd)}")
    print("=" * 60)

    # 啟動子進程
    process = subprocess.Popen(cmd)

    # 進程優先權控制：預設 NORMAL 滿血運作，僅在明確指定遊戲模式時降級
    if sys.platform == "win32":
        try:
            p = psutil.Process(process.pid)
            if game_mode_background:
                p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
                print("🛡️ [IE 防呆] 已啟用遊戲背景模式：調度為 BELOW_NORMAL 優先級。")
            else:
                p.nice(psutil.NORMAL_PRIORITY_CLASS)
                print("⚡ [滿血模式] 進程設定為 NORMAL 優先級，提供極速吞吐表現。")
        except Exception as e:
            print(f"[WARN] 調整優先權失敗: {e}")

    return process

if __name__ == "__main__":
    start_llama_engine()