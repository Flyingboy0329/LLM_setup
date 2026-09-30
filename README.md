# ⚡ LLM_setup (AI Director Studio v1.0)
> **工業工程級 NVIDIA 本地大語言模型自動化排程引擎與賽博工控工作站**  
> *Industrial-grade Local LLM Deployment & Telemetry Dashboard for Windows*

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![GUI](https://img.shields.io/badge/GUI-PyQt6-7928CA.svg)](https://riverbankcomputing.com/software/pyqt/)
[![Inference Engine](https://img.shields.io/badge/Backend-llama.cpp-00F5D4.svg)](https://github.com/ggerganov/llama.cpp)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 🌟 專案核心特色 (Key Features)

### 1. 🛡️ 零衝突背景推論守護 (Gaming & Vanguard Protection)
- **進程優先權自動降級**：後端推論進程在啟動時自動調降為 Windows 系統的 `BELOW_NORMAL_PRIORITY_CLASS`，將前台 GPU 渲染佇列完全讓行給《英雄聯盟》(LoL) 與《特戰英豪》(VALORANT) 等電競遊戲。
- **反作弊無感相容**：不使用任何 Windows Hook 或跨進程記憶體注入插件，全系統透過標準 Socket/HTTP 協議與 `llama-server` 通訊，通過 Riot Vanguard (Ring 0) 安全校驗。

### 2. 🧮 顯存耗損透明化試算 (VRAM Budget Matrix & Poka-Yoke)
- **拒絕無效參數負擔**：推論溫度直接鎖定為最佳平衡值 `0.7`，消除無效客製化認知負擔。
- **動態推薦演算法**：即時計算 `剩餘可用顯存 = 總顯存 - 模型權重體積 - 系統保留底噪 (1.5GB)`，介面直觀輸出 **`[ 推薦大小：數字 ]`**，一鍵防呆防爆顯存 (OOM)。
- **即時工額分析終端**：中央面板獨立列出模型權重基底、KV Cache 算式分解、CUDA 執行緒底噪與遊戲安全評級三色指示燈。

### 3. 🖥️ 賽博黑金電競級工控儀表板 (Cyberpunk UI)
- **硬體核心遙測**：內建自繪 CPU 環形進度條、全色溫動態水銀溫度計、RAM TANK 水箱蓄水量與磁區空間監控。
- **異構雙卡監控**：支援單卡/雙卡並行實時顯存占用、核心負載與溫度監控，自動按比例計算最佳 Tensor Split 切片參數。
- **自選模型倉庫**：點擊「選擇模型目錄」可任意掛載本機或外接硬碟的 `.gguf` 模型庫。

### 4. 🔌 模組化擴充與安全穿透 (MCP & RAG)
- **集中憑證管理**：管理員金鑰、ngrok 自訂穿透網域集中於介面直修，即改即生效。
- **輕量本機 RAG**：純 CPU 向量檢索（ChromaDB），0% 額外顯存佔用。
- **零成本外部工具**：整合 DuckDuckGo 聯網即時搜尋與台股量化指標。

---

## 🚀 快速上手 (Quick Start)

### 1. 安裝環境依賴
```powershell
git clone [https://github.com/Flyingboy0329/LLM_setup.git](https://github.com/Flyingboy0329/LLM_setup.git)
cd LLM_setup
pip install -r requirements.txt
