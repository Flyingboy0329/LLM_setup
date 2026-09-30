import os
import sys
import shutil
import subprocess
from typing import List, Dict, Any

def find_nvidia_smi() -> str:
    """動態定位 nvidia-smi 執行檔，避免依賴特定系統環境變數"""
    # 1. 檢查 PATH
    smi_path = shutil.which("nvidia-smi")
    if smi_path:
        return smi_path

    # 2. Windows 常見預設安裝路徑候選池
    candidate_paths = [
        r"C:\Windows\System32\nvidia-smi.exe",
        r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
        r"C:\Windows\SysWOW64\nvidia-smi.exe"
    ]
    for path in candidate_paths:
        if os.path.exists(path):
            return path
            
    return ""

def get_nvidia_gpus() -> List[Dict[str, Any]]:
    """
    動態取得所有 GPU 的詳細硬體遙測資料
    支援：CLI 探測與 pynvml 備援雙軌機制
    """
    smi_executable = find_nvidia_smi()
    
    if smi_executable:
        cmd = [
            smi_executable,
            "--query-gpu=index,name,memory.total,memory.free,temperature.gpu",
            "--format=csv,noheader,nounits"
        ]
        try:
            output = subprocess.check_output(cmd, encoding="utf-8").strip()
            if output:
                gpus = []
                for line in output.split("\n"):
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 5:
                        gpus.append({
                            "index": int(parts[0]),
                            "name": parts[1],
                            "total_mb": int(parts[2]),
                            "free_mb": int(parts[3]),
                            "total_gb": round(int(parts[2]) / 1024, 1),
                            "temp": int(parts[4])
                        })
                return gpus
        except Exception as e:
            print(f"[WARN] nvidia-smi CLI 查詢失敗，嘗試切換備援: {e}")

    # 備援機制：嘗試載入 pynvml
    try:
        import pynvml
        pynvml.nvmlInit()
        device_count = pynvml.nvmlDeviceGetCount()
        gpus = []
        for i in range(device_count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode("utf-8")
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            
            total_mb = int(mem_info.total / (1024 ** 2))
            free_mb = int(mem_info.free / (1024 ** 2))
            gpus.append({
                "index": i,
                "name": name,
                "total_mb": total_mb,
                "free_mb": free_mb,
                "total_gb": round(total_mb / 1024, 1),
                "temp": temp
            })
        pynvml.nvmlShutdown()
        return gpus
    except Exception as e:
        print(f"[WARN] 原生 NVML 驅動調用未果: {e}")

    return []

def calculate_hardware_plan(gpus: List[Dict[str, Any]], custom_ctx: int = None) -> Dict[str, Any]:
    gpu_count = len(gpus)
    if gpu_count == 0:
        return {
            "tier": "CPU_ONLY",
            "ngl": 0,
            "ctx": 4096,
            "tensor_split": None,
            "desc": "未偵測到 Nvidia GPU，切換至純 CPU 推論模式"
        }

    total_vram_gb = sum(g["total_gb"] for g in gpus)

    # 雙卡及多卡切片計算
    if gpu_count >= 2:
        g0_vram = gpus[0]["total_mb"]
        g1_vram = gpus[1]["total_mb"]
        # 動態計算顯存權重比，不再寫死
        ratio_str = f"{max(1, round(g0_vram / 1024))}:{max(1, round(g1_vram / 1024))}"

        if total_vram_gb <= 20:
            target_ctx = 8192
            tier = "V4-D16 (雙卡切片 16G 緊湊版)"
        elif total_vram_gb <= 36:
            target_ctx = 16384
            tier = "V5-D24 (雙卡切片 24G 旗艦版)"
        else:
            target_ctx = 32768
            tier = "V6-D48 (雙卡切片 48G 終極版)"

        return {
            "tier": tier,
            "ngl": 99,
            "ctx": custom_ctx or target_ctx,
            "tensor_split": ratio_str,
            "desc": f"雙卡平行加速，分配比率: {ratio_str}"
        }

    # 單卡規格
    vram = gpus[0]["total_gb"]
    if vram <= 9:
        return {
            "tier": "V1-S8 (單卡 8G 輕量版)",
            "ngl": 99,
            "ctx": custom_ctx or 4096,
            "tensor_split": None,
            "desc": "適配 9B 模型或收縮 Context，保留顯存給遊戲背景"
        }
    elif vram <= 13:
        return {
            "tier": "V2-S12 (單卡 12G 進階版)",
            "ngl": 99,
            "ctx": custom_ctx or 8192,
            "tensor_split": None,
            "desc": "適配 9B 長上下文或 14B Q4 模型"
        }
    elif vram <= 18:
        return {
            "tier": "V3-S16 (單卡 16G 效能版)",
            "ngl": 99,
            "ctx": custom_ctx or 16384,
            "tensor_split": None,
            "desc": "全載 14B~27B，兼顧高速推論與長歷史紀錄"
        }
    else:
        return {
            "tier": "V4-S24 (單卡 24G 滿血版)",
            "ngl": 99,
            "ctx": custom_ctx or 32768,
            "tensor_split": None,
            "desc": "滿血 32B/35B 卸載，解鎖長鏈思考與複雜任務"
        }
def get_recommended_context_size(model_file_size_gb: float, total_vram_gb: float) -> int:
    """
    IE 動態平衡算式：
    剩餘顯存 = 總顯存 - 模型權重 - CUDA 基礎底噪 (約 1.2G)
    依剩餘空間回傳推薦數值，直接回傳乾淨的數字：2048 / 4096 / 8192 / 16384 / 32768
    """
    if total_vram_gb <= 0:
        return 4096  # 純 CPU 模式建議值

    # 留 1.5GB 給系統渲染與 Discord 硬體加速
    usable_vram = total_vram_gb - 1.5
    remaining_for_kv = usable_vram - model_file_size_gb

    if remaining_for_kv >= 10.0:
        return 32768
    elif remaining_for_kv >= 5.0:
        return 16384
    elif remaining_for_kv >= 2.0:
        return 8192
    elif remaining_for_kv >= 0.8:
        return 4096
    else:
        return 2048  # 顯存極限壓榨防崩潰