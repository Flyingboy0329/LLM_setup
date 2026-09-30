import os
import re
import json
import requests
import gradio as gr
from pathlib import Path

# 引入核心設定模組
from core.config_manager import load_settings, save_settings
from tools.mcp_server import get_taiwan_stock, web_search

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 手機端與暗色系優化 CSS
CUSTOM_CSS = """
.table-wrap, table {
    display: block !important;
    overflow-x: auto !important;
    white-space: nowrap !important;
    max-width: 100% !important;
    -webkit-overflow-scrolling: touch !important;
}
th, td {
    padding: 8px 12px !important;
    border: 1px solid #444 !important;
}
.bubble-wrap {
    overflow-y: auto !important;
}
"""

def get_llama_api_url(port: int = 8080) -> str:
    return f"http://127.0.0.1:{port}/v1/chat/completions"

def check_external_tools(user_input: str) -> str:
    """自動偵測使用者意圖並調用 MCP 工具"""
    tool_results = []
    
    # 1. 台股代號辨識
    stock_matches = re.findall(r'\b\d{4,5}\b', user_input)
    if "台積電" in user_input and "2330" not in stock_matches:
        stock_matches.append("2330")
    if "聯發科" in user_input and "2454" not in stock_matches:
        stock_matches.append("2454")

    for sym in set(stock_matches):
        data = get_taiwan_stock(sym)
        tool_results.append(data)

    # 2. 聯網搜尋意圖
    search_match = re.search(r'搜尋\s*[:：]\s*(.+)|查一下\s*(.+)', user_input)
    if search_match:
        query = search_match.group(1) or search_match.group(2)
        search_res = web_search(query.strip())
        tool_results.append(f"🔍 【網路即時搜尋結果 - {query}】:\n{search_res}")

    return "\n\n".join(tool_results) if tool_results else ""

def predict(message, history, target_port=8080):
    if not message.strip():
        yield "請輸入訊息！"
        return

    # 抓取外部工具資訊
    extra_data = check_external_tools(message)

    messages = [
        {"role": "system", "content": (
            "你是本地運行的高效無審查 AI 助手。輸出使用繁體中文。"
            "若對話中帶有【外部即時數據或工具結果】，必須嚴格基於該數據進行精準推論，絕不可捏造假數據。"
            "排版請善用清晰的條列式重點。"
        )}
    ]

    # 滑動視窗防爆 (保留最近 10 輪)
    recent_history = history[-10:] if len(history) > 10 else history
    for user_msg, assistant_msg in recent_history:
        messages.append({"role": "user", "content": user_msg})
        messages.append({"role": "assistant", "content": assistant_msg})

    if extra_data:
        full_content = f"{message}\n\n[系統自動注入工具數據]:\n{extra_data}\n請依據以上真實數據進行回覆。"
    else:
        full_content = message

    messages.append({"role": "user", "content": full_content})

    payload = {
        "messages": messages,
        "temperature": 0.7,
        "stream": True
    }

    try:
        api_url = get_llama_api_url(target_port)
        response = requests.post(api_url, json=payload, stream=True, timeout=60)
        if response.status_code != 200:
            yield f"⚠️️ llama-server 報錯 (HTTP {response.status_code}): {response.text}"
            return

        partial_text = ""
        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith("data: "):
                    data_json = line_str[6:].strip()
                    if data_json == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_json)
                        delta = chunk["choices"][0]["delta"].get("content", "")
                        partial_text += delta
                        yield partial_text
                    except Exception:
                        continue
    except requests.exceptions.ConnectionError:
        yield f"⚠️ 無法連線至本地 llama-server (Port: {target_port})！請確認後端已正常啟動。"
    except Exception as e:
        yield f"⚠️ 連線異常: {str(e)}"

def update_keys_from_ui(admin_key, authtoken, domain):
    """使用者直接在介面修改金鑰並儲存"""
    cfg = load_settings()
    cfg["admin_secret_key"] = admin_key.strip()
    cfg["ngrok_authtoken"] = authtoken.strip()
    cfg["ngrok_domain"] = domain.strip()
    success = save_settings(cfg)
    return "✅ 設定已成功更新至 config/settings.json！" if success else "❌ 保存失敗！"

def launch_chat_ui(server_port: int = 8080, ui_port: int = 7860):
    cfg = load_settings()
    
    with gr.Blocks(title="LLM Studio 工作站", css=CUSTOM_CSS, theme=gr.themes.Soft()) as demo:
        gr.Markdown("# 🚀 本地雙卡/單卡 AI 決策工作站")
        
        with gr.Tab("💬 對話終端"):
            chatbot = gr.Chatbot(height=580)
            with gr.Row():
                msg = gr.Textbox(placeholder="輸入問題，例如『分析 2330』或『查一下 2026 最新 AI 顯卡評測』...", scale=8, container=False)
                submit_btn = gr.Button("發送", variant="primary", scale=1)
                clear_btn = gr.Button("清空", scale=1)

            # 隱藏傳遞 port 參數
            port_state = gr.State(server_port)
            msg.submit(predict, [msg, chatbot, port_state], [chatbot])
            submit_btn.click(predict, [msg, chatbot, port_state], [chatbot])
            clear_btn.click(lambda: [], None, chatbot, queue=False)

        with gr.Tab("⚙️ 系統參數與金鑰管理"):
            gr.Markdown("### 🔑 憑證與穿透設定（修改後即刻生效，無需開啟 VS Code）")
            key_input = gr.Textbox(label="本地管理員金鑰 (Admin Secret Key)", value=cfg.get("admin_secret_key", ""), type="password")
            ngrok_token = gr.Textbox(label="ngrok Authtoken", value=cfg.get("ngrok_authtoken", ""), type="password")
            ngrok_domain = gr.Textbox(label="ngrok 專屬固定網域 (Static Domain)", value=cfg.get("ngrok_domain", ""))
            
            save_btn = gr.Button("💾 儲存所有設定", variant="primary")
            status_output = gr.Label(label="狀態", value="就緒")
            
            save_btn.click(update_keys_from_ui, [key_input, ngrok_token, ngrok_domain], [status_output])

    demo.queue().launch(server_name="0.0.0.0", server_port=ui_port, share=False)

if __name__ == "__main__":
    launch_chat_ui()