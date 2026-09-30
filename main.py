import sys
import time
import socket
import webbrowser
from core.hardware import get_nvidia_gpus, calculate_hardware_plan, get_recommended_context_size
from core.server_runner import scan_available_models, start_llama_engine
from network.tunnel import start_ngrok_tunnel

def find_available_port(start_port: int = 8080, max_attempts: int = 20) -> int:
    """IE 防呆機制：動態偵測可用 Port，避免 8080 被佔用導致崩潰"""
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port  # 找到未被佔用的可用 Port
    return start_port

def main():
    print("""
    =======================================================
        LLM_SETUP - NVIDIA 本地部署自動化中樞
    =======================================================
    """)
    # 1. 硬體探測
    gpus = get_nvidia_gpus()
    print("🔍 [硬體掃描]")
    if not gpus:
        print(" -> 未檢測到可用 Nvidia 顯卡，啟用 CPU 模式。")
    for g in gpus:
        print(f" -> GPU {g['index']}: {g['name']} | 顯存: {g['total_gb']} GB | 溫度: {g['temp']}°C")

    plan = calculate_hardware_plan(gpus)
    print(f"\n📋 [系統判定方案] {plan['tier']}")
    print(f" -> 推薦特性: {plan['desc']}")

    # 2. 模型選取
    models = scan_available_models()
    if not models:
        print("\n❌ 錯誤：Models 資料夾內無可用的 .gguf 模型檔案！")
        print("💡 請至 Discord 討論串獲取推薦的模型下載連結，置入 ./Models/ 後重試。")
        input("\n按 Enter 鍵結束程式...")
        sys.exit(1)

    print("\n📦 [偵測到的可用本地模型清單]:")
    for idx, m in enumerate(models):
        size_gb = round(m.stat().st_size / (1024 ** 3), 2)
        print(f" [{idx + 1}] {m.name} ({size_gb} GB)")

    sel = input(f"\n請選擇要載入的模型編號 (預設 1): ").strip()
    sel_idx = int(sel) - 1 if sel.isdigit() and 1 <= int(sel) <= len(models) else 0
    chosen_model_path = models[sel_idx]
    chosen_model = chosen_model_path.name

    # 3. 上下文長度配置（動態計算推薦大小：數字）
    model_size_gb = chosen_model_path.stat().st_size / (1024 ** 3)
    total_vram = sum(g["total_gb"] for g in gpus) if gpus else 0.0
    rec_ctx = get_recommended_context_size(model_size_gb, total_vram)

    print(f"\n🧠 上下文視窗設定 [ 推薦大小：{rec_ctx} ]")
    ctx_input = input(f"請輸入 Context 長度 (直接按 Enter 套用推薦值 {rec_ctx}): ").strip()
    chosen_ctx = int(ctx_input) if ctx_input.isdigit() else rec_ctx
    print(f"👉 已套用 Context 大小: {chosen_ctx}")

    # 4. 動態尋找可用 Port
    active_port = find_available_port(8080)
    print(f"\n🔌 [連接埠分配] 鎖定推論端口: {active_port}")

    # 5. 啟動 llama-server
    print("\n🚀 正在初始化推論後端進程...")
    server_proc = start_llama_engine(model_filename=chosen_model, custom_ctx=chosen_ctx, port=active_port)
    if not server_proc:
        print("❌ 引擎啟動失敗。")
        sys.exit(1)

    time.sleep(3)
    # 動態拼接網址，杜絕寫死
    local_url = f"http://127.0.0.1:{active_port}"
    print(f"\n🌐 本機推論網頁已就緒: {local_url}")
    webbrowser.open(local_url)

    # 6. ngrok 穿透選用 (連動動態 Port)
    tunnel_choice = input("\n是否啟用 ngrok 外網穿透連線？ (y/n, 預設 n): ").strip().lower()
    if tunnel_choice == 'y':
        start_ngrok_tunnel(port=active_port)

    print("\n✅ AI 伺服器正在背景穩定運作。隨時可進行 Riot 遊戲或語音通訊。")
    print("💡 按下 Ctrl+C 可隨時中止服務並釋放顯存。")
    try:
        server_proc.wait()
    except KeyboardInterrupt:
        print("\n🛑 收到終止訊號，正在安全釋放 GPU 資源...")
        server_proc.terminate()
        server_proc.wait()
        print("✅ 顯存釋放完畢，服務已關閉。")

if __name__ == "__main__":
    main()