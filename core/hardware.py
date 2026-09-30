import os
import sys
import shutil
import subprocess
from typing import List, Dict, Any

def find_nvidia_smi() -> str:
    """動態定位 nvidia-smi 執行檔，避免依賴特定系統環境變數"""
    smi_path = shutil.which("nvidia-smi")
    if smi_path:
        return smi_path

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
    """動態取得所有 GPU 的詳細硬體遙測資料 (支援 CLI 與 pynvml 雙軌機制)"""
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

def get_recommended_context_size(model_file_size_gb: float, total_vram_gb: float) -> int:
    """
    IE 動態平衡算式：
    剩餘顯存 = 總顯存 - 模型權重 - CUDA 基礎底噪 (約 1.2G)
    """
    if total_vram_gb <= 0:
        return 4096

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
        return 2048

def calculate_hardware_plan(gpus: List[Dict[str, Any]], custom_ctx: int = None, model_size_gb: float = 0.0) -> Dict[str, Any]:
    gpu_count = len(gpus)
    if gpu_count == 0:
        return {
            "tier": "CPU_ONLY",
            "ngl": 0,
            "ctx": custom_ctx or 4096,
            "tensor_split": None,
            "desc": "未偵測到 Nvidia GPU，切換至純 CPU 推論模式"
        }

    total_vram_gb = sum(g["total_gb"] for g in gpus)
    rec_ctx = get_recommended_context_size(model_size_gb, total_vram_gb) if model_size_gb > 0 else 16384

    # 雙卡及多卡切片計算
    if gpu_count >= 2:
        g0_vram = gpus[0]["total_mb"]
        g1_vram = gpus[1]["total_mb"]
        
        # 修正：llama.cpp 標準格式使用「逗號分隔」
        ratio_str = f"{max(1, round(g0_vram / 1024))},{max(1, round(g1_vram / 1024))}"

        if total_vram_gb <= 20:
            tier = "V4-D16 (雙卡切片 16G 緊湊版)"
        elif total_vram_gb <= 36:
            tier = "V5-D24 (雙卡切片 24G 旗艦版)"
        else:
            tier = "V6-D48 (雙卡切片 48G 終極版)"

        return {
            "tier": tier,
            "ngl": 99,
            "ctx": custom_ctx or rec_ctx,
            "tensor_split": ratio_str,
            "desc": f"雙卡平行加速，分配比率: {ratio_str}"
        }

    # 單卡規格
    vram = gpus[0]["total_gb"]
    if vram <= 9:
        tier = "V1-S8 (單卡 8G 輕量版)"
    elif vram <= 13:
        tier = "V2-S12 (單卡 12G 進階版)"
    elif vram <= 18:
        tier = "V3-S16 (單卡 16G 效能版)"
    else:
        tier = "V4-S24 (單卡 24G 滿血版)"

    return {
        "tier": tier,
        "ngl": 99,
        "ctx": custom_ctx or rec_ctx,
        "tensor_split": None,
        "desc": f"單卡模式加速，顯存: {vram} GB"
    }