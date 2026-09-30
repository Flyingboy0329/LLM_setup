# ⚡ LLM_SetUp Tool [AI Director Studio v1.0]

> 專為雙卡/多卡工作站打造的賽博工控級大型語言模型 (LLM) 推論控制台。  
> 具備實時硬體遙測、VRAM 顯存動態防呆審核 (Poka-Yoke)、雙卡張量切片與 ngrok 私人外網穿透隧道。

---

## 🌟 核心特色

- 🎮 **賽博龐克工控儀表板**：深色科技介面，實時監控 CPU / RAM 水缸 / 雙 GPU 顯存與溫度 / 磁碟剩餘空間。
- ⚖️️ **動態顯存審計 (VRAM Consumption Analyzer)**：
  - 自動解析 GGUF 量化規格與模型權重基底。
  - 精確試算不同 Context 視窗下的 KV Cache 消耗與 CUDA 驅動底噪。
  - 內建安全緩衝判定，保留 $\ge 3\text{ GB}$ 顯存保障前台遊戲 (LoL / 特戰) 幀率不掉幀。
- ⚡ **雙卡張量切片 (Tensor Split)**：原生支援不同架構雙卡（如 RTX 5060 Ti + RTX 3060）負載分配，壓榨硬體極限。
- 🧠 **深度思考推理 (Reasoning) 開關**：可自由開啟思維鏈或切換為極速秒回模式。
- 🌐 **ngrok 專屬外網穿透**：一鍵開啟安全外網通道，搭配管理員金鑰，隨時隨地用手機或跨裝置調用模型。

---

## 🚀 快速開始

### 方式 1：下載綠色免安裝整合包 (推薦)
1. 前往本倉庫 **Releases** 頁面，下載最新的 LLM_Setup_Portable.zip。
2. 解壓縮至任意資料夾。
3. 將你的 .gguf 模型放入 Models/ 目錄。
4. 雙擊執行 Ahpan_LLM_Setup Tool.exe 即可啟動。

### 方式 2：使用 Python 原始碼執行
\\\ash
# 1. 複製倉庫
git clone https://github.com/<你的用戶名>/LLM_setup.git
cd LLM_setup

# 2. 安裝必要套件
pip install -r requirements.txt

# 3. 執行主程式
python gui/app_window.py
\\\

---

## 🔄 llama-server 推論引擎更新指引 (方案 B)

若 llama.cpp 官方推出新版本，你可以隨時升級引擎本體：

1. 前往官方倉庫：[llama.cpp Releases](https://github.com/ggml-org/llama.cpp/releases)。
2. 下載符合你環境的 Windows CUDA 預編譯包（例如 \llama-bXXXX-bin-win-cuda-cu12.x-x64.zip\）。
3. 將壓縮包內的 **\llama-server.exe\** 以及所有 **\*.dll\** 檔案解壓覆蓋至本專案根目錄。
4. 重開工作站，即可無痛升級最新推論核心！

---

## 🌐 私人外網連線 (Discord / 行動裝置)

1. 在主工作台點擊 **\🚀 啟動模型\**。
2. 雙擊執行根目錄下的 **\Ahpan_啟動ngrok外網穿透.bat\**。
3. 複製介面上的 **管理員金鑰** 與 ngrok 穿透網址，即可在遠端裝置或提供給好友安全使用。

---

## 🛠️ 開發與署名

- **Developer**: Pan Bo-Han (潘柏翰)
- **Architecture**: Dual-GPU Tensor Splitting / PyQt6 / llama.cpp Backend
