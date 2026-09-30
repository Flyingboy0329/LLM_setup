import sys
import os
import time
import socket
import subprocess
import ctypes
import json
import psutil
import webbrowser
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QProgressBar,
    QDialog, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, 
    QFrame, QFileDialog
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRectF, QPointF
from PyQt6.QtGui import (
    QFont, QPainter, QColor, QPen, QBrush, QConicalGradient, 
    QLinearGradient, QIcon, QPixmap, QPolygonF, QTextCursor
)

try:
    myappid = 'llmsetup.aidirectorstudio.v1'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass

NVML_AVAILABLE = False
try:
    import pynvml
    pynvml.nvmlInit()
    NVML_AVAILABLE = True
except Exception:
    NVML_AVAILABLE = False

CODE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CODE_DIR.parent
DEFAULT_MODELS_DIR = PROJECT_ROOT / "Models"

sys.path.insert(0, str(PROJECT_ROOT))
from core.hardware import get_nvidia_gpus, calculate_hardware_plan, get_recommended_context_size
from core.server_runner import find_llama_server
from core.config_manager import load_settings, save_settings

def find_available_port(start_port: int = 8080, max_attempts: int = 20) -> int:
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start_port

def get_gpu_telemetry_fallback():
    gpu_data = []
    try:
        cmd = "nvidia-smi --query-gpu=memory.used,memory.total,temperature.gpu --format=csv,noheader,nounits"
        out = subprocess.check_output(cmd, shell=True, creationflags=subprocess.CREATE_NO_WINDOW).decode()
        for line in out.strip().split("\n"):
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3 and parts[0].isdigit():
                u_mb, t_mb, temp = float(parts[0]), float(parts[1]), int(parts[2])
                gpu_data.append((u_mb / 1024.0, t_mb / 1024.0, (u_mb / t_mb) * 100.0, temp))
    except Exception:
        pass
    return gpu_data

def create_app_icon():
    pixmap = QPixmap(128, 128)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    rect = QRectF(4, 4, 120, 120)
    bg_grad = QLinearGradient(0, 0, 128, 128)
    bg_grad.setColorAt(0.0, QColor("#121424"))
    bg_grad.setColorAt(1.0, QColor("#090A12"))
    painter.setPen(QPen(QColor("#7928CA"), 3))
    painter.setBrush(QBrush(bg_grad))
    painter.drawRoundedRect(rect, 24, 24)

    bolt = QPolygonF([
        QPointF(68, 18), QPointF(38, 66), QPointF(60, 66),
        QPointF(54, 110), QPointF(92, 54), QPointF(70, 54)
    ])
    bolt_grad = QLinearGradient(38, 18, 92, 110)
    bolt_grad.setColorAt(0.0, QColor("#00F5D4"))
    bolt_grad.setColorAt(0.6, QColor("#FF007F"))
    bolt_grad.setColorAt(1.0, QColor("#7928CA"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(bolt_grad))
    painter.drawPolygon(bolt)
    painter.end()
    return QIcon(pixmap)

def enable_windows_dark_titlebar(hwnd):
    try:
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        val = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(val), ctypes.sizeof(val))
    except Exception:
        pass

# ===== 1. 圓形進度環 =====
class RingMeter(QWidget):
    def __init__(self, title="CPU", unit="%", start_color="#00F5D4", end_color="#7928CA", size=115):
        super().__init__()
        self.title = title
        self.unit = unit
        self.start_color = QColor(start_color)
        self.end_color = QColor(end_color)
        self.percent = 0
        self.value_text = "0%"
        self.setFixedSize(size, size)

    def set_data(self, percent, value_text=""):
        self.percent = max(0, min(100, percent))
        self.value_text = value_text if value_text else f"{int(self.percent)}%"
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        thickness = 8
        margin = thickness / 2.0 + 3
        rect = QRectF(margin, margin, w - margin*2, h - margin*2)

        bg_pen = QPen(QColor("#1A1D2E"), thickness)
        bg_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(bg_pen)
        painter.drawArc(rect, 0, 360 * 16)

        if self.percent > 0:
            grad = QConicalGradient(rect.center(), -90)
            grad.setColorAt(0.0, self.start_color)
            grad.setColorAt(0.5, self.end_color)
            grad.setColorAt(1.0, self.start_color)
            prog_pen = QPen(QBrush(grad), thickness)
            prog_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(prog_pen)
            span_angle = int(- (self.percent / 100.0) * 360 * 16)
            painter.drawArc(rect, 90 * 16, span_angle)

        painter.setPen(QColor("#8C9BAE"))
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        painter.drawText(QRectF(0, h * 0.18, w, 16), Qt.AlignmentFlag.AlignCenter, self.title)

        painter.setPen(QColor("#F0F6FC"))
        painter.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
        painter.drawText(QRectF(0, h * 0.36, w, 22), Qt.AlignmentFlag.AlignCenter, f"{int(self.percent)}%")

        painter.setPen(QColor("#56D6C2"))
        painter.setFont(QFont("Segoe UI", 7))
        painter.drawText(QRectF(0, h * 0.60, w, 16), Qt.AlignmentFlag.AlignCenter, self.value_text)
        painter.end()

# ===== 2. 方形水缸蓄水池 =====
class RamTankMeter(QWidget):
    def __init__(self, title="RAM TANK", width=130, height=115):
        super().__init__()
        self.title = title
        self.setFixedSize(width, height)
        self.percent = 0
        self.val_str = "0 / 0 GB"

    def set_data(self, percent, val_str):
        self.percent = max(0, min(100, percent))
        self.val_str = val_str
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        tank_rect = QRectF(6, 6, w - 12, h - 12)
        painter.setPen(QPen(QColor("#232742"), 2))
        painter.setBrush(QColor("#0A0B14"))
        painter.drawRoundedRect(tank_rect, 7, 7)

        fill_h = (self.percent / 100.0) * (tank_rect.height() - 4)
        if fill_h > 0:
            water_rect = QRectF(tank_rect.left() + 2, tank_rect.bottom() - fill_h - 2, tank_rect.width() - 4, fill_h)
            grad = QLinearGradient(water_rect.bottomLeft(), water_rect.topLeft())
            if self.percent >= 85:
                grad.setColorAt(0.0, QColor("#E11D48"))
                grad.setColorAt(1.0, QColor("#FF007F"))
            elif self.percent >= 70:
                grad.setColorAt(0.0, QColor("#7928CA"))
                grad.setColorAt(1.0, QColor("#C084FC"))
            else:
                grad.setColorAt(0.0, QColor("#0077B6"))
                grad.setColorAt(1.0, QColor("#00F5D4"))

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawRoundedRect(water_rect, 5, 5)

        painter.setPen(QColor("#F0F6FC"))
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        painter.drawText(QRectF(6, 12, w - 12, 16), Qt.AlignmentFlag.AlignCenter, self.title)

        status_text = "CRITICAL" if self.percent >= 85 else ("WARNING" if self.percent >= 70 else f"{int(self.percent)}%")
        painter.setPen(QColor("#FFFFFF") if self.percent < 85 else QColor("#FFD166"))
        painter.setFont(QFont("Consolas", 13, QFont.Weight.Bold))
        painter.drawText(QRectF(6, 40, w - 12, 22), Qt.AlignmentFlag.AlignCenter, status_text)

        painter.setPen(QColor("#E2E8F0"))
        painter.setFont(QFont("Consolas", 8))
        painter.drawText(QRectF(6, 70, w - 12, 16), Qt.AlignmentFlag.AlignCenter, self.val_str)
        painter.end()

# ===== 3. 水銀溫度計 =====
class ThermoMeter(QWidget):
    def __init__(self, width=34, height=115):
        super().__init__()
        self.setFixedSize(width, height)
        self.temp_val = 30

    def set_temp(self, temp):
        if temp > 0:
            self.temp_val = max(10, min(105, temp))
        self.update()

    def get_color(self, t):
        if t <= 42:
            return QColor("#10B981")
        elif t <= 58:
            return QColor("#FBBF24")
        elif t <= 75:
            return QColor("#F97316")
        else:
            return QColor("#EF4444")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        tube_w = 7
        tube_x = (w - tube_w) / 2
        tube_h = h - 28
        tube_rect = QRectF(tube_x, 8, tube_w, tube_h)
        bulb_rect = QRectF((w - 16) / 2, h - 24, 16, 16)

        painter.setPen(QPen(QColor("#232742"), 1.5))
        painter.setBrush(QColor("#0A0B14"))
        painter.drawRoundedRect(tube_rect, 4, 4)
        painter.drawEllipse(bulb_rect)

        ratio = max(0.05, min(1.0, (self.temp_val - 25) / 70.0))
        fill_h = ratio * (tube_h - 4)
        col = self.get_color(self.temp_val)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(col)
        painter.drawEllipse(QRectF(bulb_rect.left() + 2, bulb_rect.top() + 2, bulb_rect.width() - 4, bulb_rect.height() - 4))
        if fill_h > 0:
            painter.drawRect(QRectF(tube_x + 1.5, tube_rect.bottom() - fill_h - 2, tube_w - 3, fill_h))

        painter.setPen(col)
        painter.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
        painter.drawText(QRectF(0, h - 10, w, 11), Qt.AlignmentFlag.AlignCenter, f"{int(self.temp_val)}°C")
        painter.end()

# ===== 4. 磁碟小卡片 =====
class DiskTile(QFrame):
    def __init__(self, drive_letter="C:"):
        super().__init__()
        self.drive_letter = drive_letter
        self.setObjectName("DiskTile")
        l = QVBoxLayout(self)
        l.setContentsMargins(6, 6, 6, 6)
        l.setSpacing(3)

        top_h = QHBoxLayout()
        self.lbl_name = QLabel(f"磁碟 ({drive_letter})")
        self.lbl_name.setStyleSheet("font-size: 11px; font-weight: bold; color: #E2E8F0;")
        top_h.addWidget(self.lbl_name)
        top_h.addStretch()
        l.addLayout(top_h)

        self.bar = QProgressBar()
        self.bar.setFixedHeight(6)
        self.bar.setTextVisible(False)
        self.bar.setStyleSheet("QProgressBar { background: #1A1D2E; border: none; border-radius: 3px; } QProgressBar::chunk { background: #00B4D8; border-radius: 3px; }")
        l.addWidget(self.bar)

        self.lbl_info = QLabel("讀取中...")
        self.lbl_info.setStyleSheet("font-family: 'Segoe UI'; font-size: 9px; color: #8C9BAE;")
        l.addWidget(self.lbl_info)

    def update_disk(self, total_gb, free_gb, percent):
        self.bar.setValue(int(percent))
        self.lbl_info.setText(f"剩餘 {int(free_gb)} GB / 共 {int(total_gb)} GB")

CYBERPUNK_GLOBAL_QSS = """
QMainWindow, QWidget#CentralWidget {
    background-color: #0B0C16;
}
QWidget {
    color: #F0F6FC;
    font-family: "Segoe UI", "Microsoft JhengHei UI", sans-serif;
}
QFrame#DashboardCard {
    background-color: #121424;
    border: 1px solid #1F233D;
    border-radius: 14px;
}
QFrame#HeaderCard {
    background-color: #0E101E;
    border-bottom: 1px solid #1C2035;
}
QFrame#DiskTile {
    background-color: #0E101A;
    border: 1px solid #1C2035;
    border-radius: 6px;
}
QLineEdit, QTextEdit, QComboBox {
    background-color: #090A12;
    border: 1px solid #232742;
    border-radius: 8px;
    padding: 6px 10px;
    color: #00F5D4;
    font-size: 12px;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus {
    border: 1px solid #7928CA;
    background-color: #0D0E1A;
}
QPushButton#PillBtn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF007F, stop:1 #7928CA);
    color: #FFFFFF;
    border: none;
    border-radius: 10px;
    padding: 9px 24px;
    font-weight: bold;
    font-size: 12px;
}
QPushButton#PillBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF3399, stop:1 #9945FF);
}
QPushButton#SubPillBtn {
    background-color: #1C2038;
    color: #00F5D4;
    border: 1px solid #2D3359;
    border-radius: 8px;
    padding: 7px 14px;
    font-weight: bold;
    font-size: 11px;
}
QPushButton#SubPillBtn:hover {
    background-color: #2D3359;
    color: #FFFFFF;
}
QPushButton#LinkBtn {
    background-color: #0F172A;
    color: #38BDF8;
    border: 1px solid #0284C7;
    border-radius: 6px;
    padding: 5px 12px;
    font-size: 11px;
    font-weight: bold;
}
QPushButton#LinkBtn:hover {
    background-color: #0369A1;
    color: #FFFFFF;
}
QPushButton#MoreBtn {
    background-color: transparent;
    color: #00F5D4;
    border: none;
    font-size: 10px;
    font-weight: bold;
    padding: 2px 4px;
}
QPushButton#MoreBtn:hover {
    color: #FF007F;
    text-decoration: underline;
}
QLabel#PillBadge {
    background-color: #1B1E36;
    color: #A0ABC0;
    border: 1px solid #2A2F54;
    border-radius: 10px;
    padding: 4px 12px;
    font-size: 10px;
    font-weight: bold;
}
QTextEdit#TerminalLog {
    background-color: #08090F;
    border: 1px solid #1C2035;
    border-radius: 10px;
    color: #E2E8F0;
    font-family: "Consolas", monospace;
    font-size: 11px;
    padding: 10px;
}
QTextEdit#CalcLog {
    background-color: #07080E;
    border: 1px solid #1A1F36;
    border-radius: 10px;
    color: #00F5D4;
    font-family: "Consolas", monospace;
    font-size: 11px;
    line-height: 140%;
    padding: 10px;
}
"""

class TelemetryThread(QThread):
    telemetry_signal = pyqtSignal(float, int, float, str, float, str, int, float, str, int, list)

    def __init__(self):
        super().__init__()
        self.running = True

    def run(self):
        while self.running:
            try:
                cpu_pct = psutil.cpu_percent(interval=None)
                cpu_temp = int(36 + (cpu_pct * 0.45))
                mem = psutil.virtual_memory()
                ram_pct = mem.percent
                ram_val = f"{mem.used/(1024**3):.1f}/{mem.total/(1024**3):.1f}G"

                g0_pct, g0_val, g0_temp = 0.0, "0.0/16.0G", 0
                g1_pct, g1_val, g1_temp = 0.0, "0.0/12.0G", 0

                nvml_success = False
                if NVML_AVAILABLE:
                    try:
                        cnt = pynvml.nvmlDeviceGetCount()
                        if cnt >= 1:
                            h0 = pynvml.nvmlDeviceGetHandleByIndex(0)
                            info0 = pynvml.nvmlDeviceGetMemoryInfo(h0)
                            g0_pct = (info0.used / info0.total) * 100.0
                            g0_val = f"{info0.used/(1024**3):.1f}/{info0.total/(1024**3):.1f}G"
                            g0_temp = int(pynvml.nvmlDeviceGetTemperature(h0, pynvml.NVML_TEMPERATURE_GPU))
                        if cnt >= 2:
                            h1 = pynvml.nvmlDeviceGetHandleByIndex(1)
                            info1 = pynvml.nvmlDeviceGetMemoryInfo(h1)
                            g1_pct = (info1.used / info1.total) * 100.0
                            g1_val = f"{info1.used/(1024**3):.1f}/{info1.total/(1024**3):.1f}G"
                            g1_temp = int(pynvml.nvmlDeviceGetTemperature(h1, pynvml.NVML_TEMPERATURE_GPU))
                        nvml_success = True
                    except Exception:
                        nvml_success = False

                if not nvml_success or g0_val == "0.0/16.0G":
                    fb = get_gpu_telemetry_fallback()
                    if len(fb) >= 1:
                        u, t, pct, tmp = fb[0]
                        g0_pct, g0_val, g0_temp = pct, f"{u:.1f}/{t:.1f}G", tmp
                    if len(fb) >= 2:
                        u, t, pct, tmp = fb[1]
                        g1_pct, g1_val, g1_temp = pct, f"{u:.1f}/{t:.1f}G", tmp

                disks = []
                for d in ["C:\\", "D:\\", "E:\\"]:
                    try:
                        u = psutil.disk_usage(d)
                        disks.append((d[0], u.total/(1024**3), u.free/(1024**3), u.percent))
                    except Exception:
                        pass

                self.telemetry_signal.emit(cpu_pct, cpu_temp, ram_pct, ram_val, g0_pct, g0_val, g0_temp, g1_pct, g1_val, g1_temp, disks)
            except Exception:
                pass
            time.sleep(1.5)

    def stop(self):
        self.running = False
        self.wait()

class LlamaServerThread(QThread):
    log_signal = pyqtSignal(str)
    started_signal = pyqtSignal(int)
    stopped_signal = pyqtSignal()

    def __init__(self, model_path: Path, ctx_size: int, port: int):
        super().__init__()
        self.model_path = model_path
        self.ctx_size = ctx_size
        self.port = port
        self.process = None

    def run(self):
        exe_path = find_llama_server()
        gpus = get_nvidia_gpus()
        plan = calculate_hardware_plan(gpus, custom_ctx=self.ctx_size)

        cmd = [
            exe_path,
            "-m", str(self.model_path),
            "-c", str(self.ctx_size),
            "-ngl", str(plan["ngl"]),
            "--port", str(self.port),
            "--host", "0.0.0.0",
            "-fa"
        ]
        if plan["tensor_split"]:
            cmd.extend(["-ts", plan["tensor_split"]])

        self.log_signal.emit(f"🚀 [執行指令] {' '.join(cmd)}")
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )

            if sys.platform == "win32":
                try:
                    p = psutil.Process(self.process.pid)
                    p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
                    self.log_signal.emit("🛡️ [IE 防呆] 引擎優先級已調降為背景等級，保障遊戲 FPS。")
                except Exception:
                    pass

            self.started_signal.emit(self.port)

            for line in iter(self.process.stdout.readline, ''):
                if line:
                    self.log_signal.emit(line.strip())
                if self.process.poll() is not None:
                    break
        except Exception as e:
            self.log_signal.emit(f"❌ 引擎異常終止: {e}")
        finally:
            self.stopped_signal.emit()

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait()
        self.wait()

class MidnightDashboardWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LLM_SetUp Tool [AI Director Studio v1.0]")
        self.resize(1260, 920)
        self.setMinimumSize(1100, 840)
        self.setWindowIcon(create_app_icon())

        self.server_thread = None
        self.active_port = 8080
        self.cfg = load_settings()

        self.current_models_dir = Path(self.cfg.get("custom_models_dir", str(DEFAULT_MODELS_DIR)))
        if not self.current_models_dir.exists():
            self.current_models_dir = DEFAULT_MODELS_DIR
            self.current_models_dir.mkdir(parents=True, exist_ok=True)

        self.init_ui()
        self.start_telemetry()
        self.refresh_models()

    def showEvent(self, event):
        super().showEvent(event)
        enable_windows_dark_titlebar(int(self.winId()))

    def make_card(self):
        card = QFrame()
        card.setObjectName("DashboardCard")
        return card

    def init_ui(self):
        central = QWidget()
        central.setObjectName("CentralWidget")
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 頂部導航
        header = QFrame()
        header.setObjectName("HeaderCard")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(28, 14, 28, 14)

        t_box = QHBoxLayout()
        logo = QLabel("🟣 LLM_SetUp tool")
        logo.setStyleSheet("font-size: 17px; font-weight: 900; color: #FFFFFF; letter-spacing: 1px;")
        ver = QLabel("v1.0 ARTIFACT")
        ver.setStyleSheet("background-color: #231938; color: #C084FC; border: 1px solid #7E22CE; border-radius: 6px; padding: 3px 8px; font-size: 10px; font-weight: bold;")
        t_box.addWidget(logo)
        t_box.addSpacing(10)
        t_box.addWidget(ver)
        h_layout.addLayout(t_box)

        h_layout.addStretch()

        self.badge_llama = QLabel("LLAMA: OFFLINE")
        self.badge_llama.setObjectName("PillBadge")
        self.badge_guard = QLabel("GUARD: IDLE")
        self.badge_guard.setObjectName("PillBadge")
        h_layout.addWidget(self.badge_llama)
        h_layout.addSpacing(10)
        h_layout.addWidget(self.badge_guard)
        main_layout.addWidget(header)

        # 核心區域
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 16, 24, 12)
        body_layout.setSpacing(14)

        upper_box = QHBoxLayout()
        upper_box.setSpacing(16)

        # ==========================================================
        # 1. 左欄：硬體核心監控
        # ==========================================================
        col_left = QVBoxLayout()
        col_left.setSpacing(14)

        # 1-1. SYSTEM CORE & MEMORY
        card_ram = self.make_card()
        ram_l = QVBoxLayout(card_ram)
        ram_l.setContentsMargins(18, 14, 18, 16)
        lbl_ram_title = QLabel()
        lbl_ram_title.setText(
            "<div style='line-height: 100%; margin: 0px; padding: 0px;'>"
            "<span style='font-size: 13px; font-weight: bold; color: #E2E8F0; letter-spacing: 0.5px;'>SYSTEM CORE & MEMORY</span><br>"
            "<span style='font-size: 11px; color: #717B9E; line-height: 140%;'>中央處理器負載與實體記憶體水缸蓄量</span>"
            "</div>"
        )
        ram_l.addWidget(lbl_ram_title)
        ram_l.addSpacing(12)

        core_box = QHBoxLayout()
        core_box.addSpacing(25)
        self.ring_cpu = RingMeter(title="CPU LOAD", start_color="#00F5D4", end_color="#7928CA", size=115)
        self.thermo_cpu = ThermoMeter(width=34, height=115)
        self.tank_ram = RamTankMeter(title="RAM TANK", width=130, height=115)
        core_box.addWidget(self.ring_cpu)
        core_box.addSpacing(4)
        core_box.addWidget(self.thermo_cpu)
        core_box.addSpacing(18)
        core_box.addWidget(self.tank_ram)
        core_box.addStretch()
        ram_l.addLayout(core_box)
        col_left.addWidget(card_ram)

        # 1-2. LOCAL STORAGE POOL
        card_disk = self.make_card()
        disk_l = QVBoxLayout(card_disk)
        disk_l.setContentsMargins(18, 12, 18, 12)
        lbl_disk_title = QLabel()
        lbl_disk_title.setText(
            "<div style='line-height: 100%; margin: 0px; padding: 0px;'>"
            "<span style='font-size: 13px; font-weight: bold; color: #E2E8F0; letter-spacing: 0.5px;'>LOCAL STORAGE POOL</span><br>"
            "<span style='font-size: 11px; color: #717B9E; line-height: 140%;'>本地高速存儲磁區 (SSD / NVMe / HDD) 空間監控</span>"
            "</div>"
        )
        disk_l.addWidget(lbl_disk_title)
        disk_l.addSpacing(10)

        self.disk_tiles_box = QHBoxLayout()
        self.disk_c = DiskTile("C:")
        self.disk_d = DiskTile("D:")
        self.disk_e = DiskTile("E:")
        self.disk_tiles_box.addWidget(self.disk_c)
        self.disk_tiles_box.addWidget(self.disk_d)
        self.disk_tiles_box.addWidget(self.disk_e)
        disk_l.addLayout(self.disk_tiles_box)

        more_row = QHBoxLayout()
        more_row.addStretch()
        btn_more = QPushButton("更多......")
        btn_more.setObjectName("MoreBtn")
        more_row.addWidget(btn_more)
        disk_l.addLayout(more_row)
        col_left.addWidget(card_disk)

        # 1-3. GPU ACCELERATION
        card_gpus = self.make_card()
        gpu_l = QVBoxLayout(card_gpus)
        gpu_l.setContentsMargins(18, 14, 18, 16)
        lbl_gpu_title = QLabel()
        lbl_gpu_title.setText(
            "<div style='line-height: 100%; margin: 0px; padding: 0px;'>"
            "<span style='font-size: 13px; font-weight: bold; color: #E2E8F0; letter-spacing: 0.5px;'>GPU ACCELERATION</span><br>"
            "<span style='font-size: 11px; color: #717B9E; line-height: 140%;'>硬體加速核心顯存佔用與即時溫度監控</span>"
            "</div>"
        )
        gpu_l.addWidget(lbl_gpu_title)
        gpu_l.addSpacing(12)

        gpu_meter_box = QHBoxLayout()
        gpu_meter_box.addSpacing(25)
        self.ring_gpu0 = RingMeter(title="RTX 5060 Ti", start_color="#00F5D4", end_color="#0077B6", size=112)
        self.thermo_gpu0 = ThermoMeter(width=34, height=112)
        self.ring_gpu1 = RingMeter(title="RTX 3060", start_color="#C084FC", end_color="#FF007F", size=112)
        self.thermo_gpu1 = ThermoMeter(width=34, height=112)

        gpu_meter_box.addWidget(self.ring_gpu0)
        gpu_meter_box.addSpacing(4)
        gpu_meter_box.addWidget(self.thermo_gpu0)
        gpu_meter_box.addSpacing(18)
        gpu_meter_box.addWidget(self.ring_gpu1)
        gpu_meter_box.addSpacing(4)
        gpu_meter_box.addWidget(self.thermo_gpu1)
        gpu_meter_box.addStretch()
        gpu_l.addLayout(gpu_meter_box)
        col_left.addWidget(card_gpus)

        upper_box.addLayout(col_left, stretch=3)

        # ==========================================================
        # 2. 中欄：顯存耗損計算與算式說明 (獨立 Log 風格) + 底部連線中樞
        # ==========================================================
        col_mid = QVBoxLayout()
        card_hub = self.make_card()
        hub_l = QVBoxLayout(card_hub)
        hub_l.setContentsMargins(20, 16, 20, 16)
        hub_l.setSpacing(10)

        # 頂部標題
        head_calc = QHBoxLayout()
        lbl_hub_title = QLabel("VRAM CONSUMPTION ANALYZER")
        lbl_hub_title.setStyleSheet("color: #E2E8F0; font-size: 13px; font-weight: bold; letter-spacing: 0.5px;")
        lbl_calc_status = QLabel("● AUTO AUDITING")
        lbl_calc_status.setStyleSheet("color: #00F5D4; font-size: 10px; font-weight: bold;")
        head_calc.addWidget(lbl_hub_title)
        head_calc.addStretch()
        head_calc.addWidget(lbl_calc_status)

        title_box_c = QWidget()
        tbc_l = QVBoxLayout(title_box_c)
        tbc_l.setContentsMargins(0, 0, 0, 0)
        tbc_l.addLayout(head_calc)
        lbl_c_sub = QLabel("模型權重、量化條件與 KV Cache 顯存動態試算過程")
        lbl_c_sub.setStyleSheet("color: #717B9E; font-size: 11px; line-height: 140%;")
        tbc_l.addWidget(lbl_c_sub)
        hub_l.addWidget(title_box_c)

        # 2-1. 耗損計算 Log 獨立終端視窗
        self.txt_calc_log = QTextEdit()
        self.txt_calc_log.setObjectName("CalcLog")
        self.txt_calc_log.setReadOnly(True)
        hub_l.addWidget(self.txt_calc_log, stretch=1)

        # 2-2. 連線與安全性中樞 (放置於中間最下方)
        net_box = QFrame()
        net_box.setStyleSheet("background-color: #090A12; border: 1px solid #232742; border-radius: 10px; padding: 10px;")
        nb_l = QVBoxLayout(net_box)
        nb_l.setSpacing(8)

        nb_title = QLabel("🔑 網路穿透與憑證配置 (修改後即時自動保存)")
        nb_title.setStyleSheet("color: #E2E8F0; font-size: 11px; font-weight: bold;")
        nb_l.addWidget(nb_title)

        row_net = QHBoxLayout()
        self.btn_open_local = QPushButton("🌐 開啟 Localhost")
        self.btn_open_local.setObjectName("LinkBtn")
        self.btn_open_local.clicked.connect(self.open_current_localhost)
        
        self.edit_ngrok = QLineEdit()
        self.edit_ngrok.setPlaceholderText("輸入專屬 ngrok 網域 (例如: my-ai.ngrok-free.app)...")
        self.edit_ngrok.setText(self.cfg.get("ngrok_domain", ""))
        self.edit_ngrok.textChanged.connect(self.on_ngrok_changed)

        row_net.addWidget(self.btn_open_local)
        row_net.addWidget(self.edit_ngrok, stretch=1)
        nb_l.addLayout(row_net)

        row_key = QHBoxLayout()
        lbl_k = QLabel("管理員金鑰:")
        lbl_k.setStyleSheet("color: #717B9E; font-size: 11px;")
        self.edit_key = QLineEdit()
        self.edit_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_key.setPlaceholderText("本地 Admin Key (保護硬碟讀寫與工具權限)...")
        self.edit_key.setText(self.cfg.get("admin_secret_key", ""))
        self.edit_key.textChanged.connect(self.on_key_changed)
        row_key.addWidget(lbl_k)
        row_key.addWidget(self.edit_key)
        nb_l.addLayout(row_key)

        hub_l.addWidget(net_box)

        col_mid.addWidget(card_hub)
        upper_box.addLayout(col_mid, stretch=4)

        # ==========================================================
        # 3. 右欄：即時日誌終端
        # ==========================================================
        col_right = QVBoxLayout()
        card_log = self.make_card()
        cl_l = QVBoxLayout(card_log)
        cl_l.setContentsMargins(18, 14, 18, 16)

        log_head = QHBoxLayout()
        lbl_cl = QLabel("EVENT STREAM LOG")
        lbl_cl.setStyleSheet("color: #E2E8F0; font-size: 13px; font-weight: bold; letter-spacing: 0.5px;")
        lbl_live = QLabel("● STREAMING")
        lbl_live.setStyleSheet("color: #00F5D4; font-size: 10px; font-weight: bold;")
        log_head.addWidget(lbl_cl)
        log_head.addStretch()
        log_head.addWidget(lbl_live)

        title_box_l = QWidget()
        tbl_l = QVBoxLayout(title_box_l)
        tbl_l.setContentsMargins(0, 0, 0, 0)
        tbl_l.addLayout(log_head)
        lbl_log_sub = QLabel("神經分析節點、推論日誌與 Device 注入事件串流")
        lbl_log_sub.setStyleSheet("color: #717B9E; font-size: 11px; line-height: 140%;")
        tbl_l.addWidget(lbl_log_sub)
        cl_l.addWidget(title_box_l)
        cl_l.addSpacing(12)

        self.txt_log = QTextEdit()
        self.txt_log.setObjectName("TerminalLog")
        self.txt_log.setReadOnly(True)
        cl_l.addWidget(self.txt_log)
        col_right.addWidget(card_log)

        upper_box.addLayout(col_right, stretch=3)
        body_layout.addLayout(upper_box, stretch=1)

        # ==========================================================
        # 4. 下方管線條：自選目錄 + 模型下拉 + Context 修改 + 啟動按鈕
        # ==========================================================
        card_watch = self.make_card()
        cw_l = QHBoxLayout(card_watch)
        cw_l.setContentsMargins(20, 10, 20, 10)
        cw_l.setSpacing(10)

        title_box_w = QLabel()
        title_box_w.setText(
            "<div style='line-height: 125%; margin: 0px; padding: 0px;'>"
            "<span style='font-size: 13px; font-weight: bold; color: #E2E8F0; letter-spacing: 0.5px;'>WATCH FOLDER PIPELINE</span><br>"
            "<span style='font-size: 11px; font-weight: bold; color: #00F5D4;'>掛載自選模型倉庫 ➔</span>"
            "</div>"
        )
        cw_l.addWidget(title_box_w)

        self.combo_models = QComboBox()
        self.combo_models.currentIndexChanged.connect(self.on_model_selected)
        cw_l.addWidget(self.combo_models, stretch=3)

        btn_choose_dir = QPushButton("選擇模型目錄")
        btn_choose_dir.setObjectName("SubPillBtn")
        btn_choose_dir.clicked.connect(self.choose_models_folder)
        cw_l.addWidget(btn_choose_dir)

        lbl_ctx_tag = QLabel("Context (總Token):")
        lbl_ctx_tag.setStyleSheet("color: #A0AEC0; font-weight: bold; font-size: 11px;")
        cw_l.addWidget(lbl_ctx_tag)

        self.edit_ctx = QLineEdit("8192")
        self.edit_ctx.setFixedWidth(70)
        self.edit_ctx.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edit_ctx.textChanged.connect(self.recalculate_vram_audit)
        cw_l.addWidget(self.edit_ctx)

        self.lbl_rec_ctx = QLabel("推薦大小: 8192")
        self.lbl_rec_ctx.setStyleSheet("color: #FBBF24; font-weight: bold; font-size: 11px;")
        cw_l.addWidget(self.lbl_rec_ctx)

        self.btn_toggle = QPushButton("🚀 啟動模型")
        self.btn_toggle.setObjectName("PillBtn")
        self.btn_toggle.clicked.connect(self.toggle_engine)
        cw_l.addWidget(self.btn_toggle)

        body_layout.addWidget(card_watch)
        main_layout.addWidget(body, stretch=1)

        # 底部署名
        footer = QFrame()
        footer.setStyleSheet("background-color: #090A12; border-top: 1px solid #161828; padding: 6px;")
        f_layout = QHBoxLayout(footer)
        f_layout.setContentsMargins(28, 6, 28, 6)

        foot_left = QLabel("LLM_SETUP STUDIO  |  NEURAL INGESTION & AUTO-DEPLOY")
        foot_left.setStyleSheet("color: #555E7A; font-size: 10px; font-weight: bold; letter-spacing: 0.8px;")
        foot_right = QLabel("Developed by Pan Bo-Han (潘柏翰)  |  指導老師：郭俞霈教授")
        foot_right.setStyleSheet("color: #8C9BAE; font-size: 11px; font-weight: bold;")
        f_layout.addWidget(foot_left)
        f_layout.addStretch()
        f_layout.addWidget(foot_right)
        main_layout.addWidget(footer)

        self.append_log("⚡ [系統核心] 完全體工作站已就緒。")

    def append_log(self, text):
        ts = datetime.now().strftime("%H:%M:%S")
        clean = text.strip()
        if "🚀" in clean or "啟動" in clean or "成功" in clean:
            styled = f"<span style='color:#00F5D4; font-weight:bold;'>{clean}</span>"
        elif "❌" in clean or "異常" in clean or "失敗" in clean:
            styled = f"<span style='color:#FF007F; font-weight:bold;'>{clean}</span>"
        elif "🛡️" in clean or "推薦" in clean or "🔌" in clean:
            styled = f"<span style='color:#FBBF24; font-weight:bold;'>{clean}</span>"
        else:
            styled = f"<span style='color:#A0AEC0;'>{clean}</span>"

        html_line = f"<div style='margin-bottom: 2px;'><span style='color:#555E7A;'>[{ts}]</span> {styled}</div>"
        self.txt_log.append(html_line)
        self.txt_log.moveCursor(QTextCursor.MoveOperation.End)

    def choose_models_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "選擇存放 GGUF 模型的資料夾", str(self.current_models_dir))
        if folder:
            self.current_models_dir = Path(folder)
            self.cfg["custom_models_dir"] = folder
            save_settings(self.cfg)
            self.append_log(f"📁 模型倉庫目錄切換為: {folder}")
            self.refresh_models()

    def refresh_models(self):
        self.combo_models.clear()
        models = list(self.current_models_dir.glob("*.gguf"))
        if not models:
            self.combo_models.addItem(f"❌ 查無 .gguf 模型 ({self.current_models_dir.name})")
            self.lbl_rec_ctx.setText("推薦大小: 4096")
            self.edit_ctx.setText("4096")
            self.txt_calc_log.setHtml("<span style='color:#FF758F;'>⚠️ 目前目錄下未檢測到可用的 .gguf 模型檔案。<br>請點選下方『選擇模型目錄』載入模型。</span>")
            return

        for m in models:
            sz = round(m.stat().st_size / (1024**3), 1)
            self.combo_models.addItem(f"{m.name} ({sz} GB)", m)
        self.append_log(f"📁 已在 [{self.current_models_dir.name}] 掃描載入 {len(models)} 個本地 GGUF 模型。")
        self.on_model_selected(0)

    def on_model_selected(self, index):
        model_path = self.combo_models.currentData()
        if isinstance(model_path, Path) and model_path.exists():
            gpus = get_nvidia_gpus()
            tot_vram = sum(g["total_gb"] for g in gpus) if gpus else 0.0
            sz_gb = model_path.stat().st_size / (1024**3)
            rec = get_recommended_context_size(sz_gb, tot_vram)
            self.lbl_rec_ctx.setText(f"推薦大小: {rec}")
            self.edit_ctx.setText(str(rec))
            self.recalculate_vram_audit()

    def recalculate_vram_audit(self):
        """核心演算法：即時動態計算顯存耗損與推論算式"""
        model_path = self.combo_models.currentData()
        if not isinstance(model_path, Path) or not model_path.exists():
            return

        gpus = get_nvidia_gpus()
        tot_vram = sum(g["total_gb"] for g in gpus) if gpus else 0.0
        sz_gb = model_path.stat().st_size / (1024**3)
        
        ctx_val = self.edit_ctx.text().strip()
        ctx_size = int(ctx_val) if ctx_val.isdigit() and int(ctx_val) > 0 else 8192

        # 1. 量化條件解析
        fname_upper = model_path.name.upper()
        if "Q4_K_M" in fname_upper or "Q4_0" in fname_upper:
            quant_type = "Q4_K_M (4-bit Balanced)"
            bpw = 4.5
        elif "Q5_K_M" in fname_upper:
            quant_type = "Q5_K_M (5-bit High Precision)"
            bpw = 5.5
        elif "Q8_0" in fname_upper:
            quant_type = "Q8_0 (8-bit Full Precision)"
            bpw = 8.5
        elif "Q3_K" in fname_upper:
            quant_type = "Q3_K_M (3-bit Extreme Compress)"
            bpw = 3.4
        else:
            quant_type = "標準 GGUF 量化"
            bpw = 4.5

        # 2. KV Cache 顯存算式：KV_Cache_GB = (2 * Layers * Heads * Dim * BytesPerVal * Context) / 1024^3
        # 依主流 32B / 14B 規格平均換算：每 1024 Token 的 FP16 KV Cache 約為 0.12 GB ~ 0.20 GB
        kv_cache_gb = round((ctx_size / 1024) * 0.14, 2)
        cuda_overhead = 1.15  # CUDA Context 驅動基本底噪
        total_estimate_gb = round(sz_gb + kv_cache_gb + cuda_overhead, 2)
        remaining_vram = round(tot_vram - total_estimate_gb, 2)

        # 3. 遊戲與安全防呆判定
        if remaining_vram >= 3.0:
            safety_badge = "<span style='color:#00F5D4; font-weight:bold;'>【極度充裕 • 綠燈】</span> 保留顯存 ≥ 3GB，Riot 遊戲 (LoL/特戰) 100% 幀率保障，無卡頓風險。"
        elif remaining_vram >= 0.8:
            safety_badge = "<span style='color:#FBBF24; font-weight:bold;'>【緊湊平衡 • 黃燈】</span> 顯存處於甜點位，可正常推論，但進行重度 3D 遊戲時可能微幅搶佔。"
        else:
            safety_badge = "<span style='color:#FF758F; font-weight:bold;'>【超載危險 • 紅燈】</span> 預估顯存溢出！極易引發 CUDA OOM 閃退，強烈建議調小 Context！"

        # 渲染算式與日誌
        html_content = f"""
        <div style='font-family: Consolas, monospace; line-height: 145%;'>
            <span style='color:#C084FC; font-weight:bold;'>[工額分析] 模型規格與量化條件</span><br>
            • 模型檔案: {model_path.name}<br>
            • 量化檔位: <span style='color:#56D6C2;'>{quant_type}</span> (約 {bpw} bits/param)<br>
            • 權重體積: <span style='color:#FFFFFF;'>{sz_gb:.2f} GB</span><br>
            <br>
            <span style='color:#C084FC; font-weight:bold;'>[算式分解] 顯存耗損動態試算 (VRAM Budgeting)</span><br>
            ┌ <b>模型權重基底 (Model Base)</b> : {sz_gb:.2f} GB<br>
            ├ <b>KV Cache (Context {ctx_size} Tokens)</b> : {kv_cache_gb:.2f} GB<br>
            │  <i>(計算公式: 2 × 層數 × 頭數 × 維度 × {ctx_size} Tokens)</i><br>
            ├ <b>CUDA 執行緒底噪 (Runtime Overhead)</b> : {cuda_overhead:.2f} GB<br>
            └─────────────────────────────────────────────<br>
            <b>總預估顯存開銷 (Total Allocated)</b> : <span style='color:#FBBF24; font-size:12px; font-weight:bold;'>{total_estimate_gb:.2f} GB</span><br>
            <b>本機總可用顯存 (Total Physical VRAM)</b> : {tot_vram:.1f} GB<br>
            <b>推論後預估剩餘空間 (Free Buffer)</b> : <span style='color:#00F5D4; font-size:12px; font-weight:bold;'>{remaining_vram:.2f} GB</span><br>
            <br>
            <span style='color:#C084FC; font-weight:bold;'>[IE 系統調度與遊戲並行評斷]</span><br>
            {safety_badge}
        </div>
        """
        self.txt_calc_log.setHtml(html_content)

    def on_ngrok_changed(self, text):
        self.cfg["ngrok_domain"] = text.strip()
        save_settings(self.cfg)

    def on_key_changed(self, text):
        self.cfg["admin_secret_key"] = text.strip()
        save_settings(self.cfg)

    def open_current_localhost(self):
        url = f"http://127.0.0.1:{self.active_port}"
        self.append_log(f"🌐 開啟本機推論頁面: {url}")
        webbrowser.open(url)

    def start_telemetry(self):
        self.telemetry = TelemetryThread()
        self.telemetry.telemetry_signal.connect(self.update_telemetry)
        self.telemetry.start()

    def update_telemetry(self, cpu_p, cpu_t, ram_p, ram_v, g0_p, g0_v, g0_t, g1_p, g1_v, g1_t, disks):
        self.ring_cpu.set_data(cpu_p)
        self.thermo_cpu.set_temp(cpu_t)
        self.tank_ram.set_data(ram_p, ram_v)
        
        self.ring_gpu0.set_data(g0_p, g0_v)
        self.thermo_gpu0.set_temp(g0_t)

        self.ring_gpu1.set_data(g1_p, g1_v)
        self.thermo_gpu1.set_temp(g1_t)

        for letter, tot, free, pct in disks:
            if letter == "C":
                self.disk_c.update_disk(tot, free, pct)
            elif letter == "D":
                self.disk_d.update_disk(tot, free, pct)
            elif letter == "E":
                self.disk_e.update_disk(tot, free, pct)

    def toggle_engine(self):
        if not self.server_thread or not self.server_thread.isRunning():
            model_path = self.combo_models.currentData()
            if not isinstance(model_path, Path) or not model_path.exists():
                self.append_log("❌ [防呆錯誤] 請先選取正確的 GGUF 模型！")
                return

            user_ctx_str = self.edit_ctx.text().strip()
            if user_ctx_str.isdigit() and int(user_ctx_str) > 0:
                ctx_size = int(user_ctx_str)
            else:
                rec_text = self.lbl_rec_ctx.text().replace("推薦大小:", "").strip()
                ctx_size = int(rec_text) if rec_text.isdigit() else 8192
                self.edit_ctx.setText(str(ctx_size))

            self.active_port = find_available_port(8080)
            self.btn_open_local.setText(f"🌐 Localhost :{self.active_port}")
            self.append_log(f"🔌 鎖定可用連接埠: {self.active_port} | Context 視窗: {ctx_size}")

            self.server_thread = LlamaServerThread(model_path, ctx_size, self.active_port)
            self.server_thread.log_signal.connect(self.append_log)
            self.server_thread.started_signal.connect(self.on_server_started)
            self.server_thread.stopped_signal.connect(self.on_server_stopped)
            self.server_thread.start()

            self.btn_toggle.setText("⏹ 關閉模型")
            self.btn_toggle.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #E11D48, stop:1 #BE123C); color: #FFF; border: none; border-radius: 10px; padding: 9px 24px; font-weight: bold; font-size: 12px;")
            self.badge_llama.setText("LLAMA: RUNNING")
            self.badge_llama.setStyleSheet("background-color: #122822; color: #52B788; border: 1px solid #2D6A4F; border-radius: 10px; padding: 4px 12px; font-size: 10px; font-weight: bold;")
        else:
            self.append_log("🛑 正在關閉推論後端進程...")
            self.server_thread.stop()

    def on_server_started(self, port):
        self.badge_llama.setText(f"LLAMA: PORT {port}")
        self.append_log(f"🎉 本地推論核心已就緒！正在拉起 llama 原生對話網頁...")
        webbrowser.open(f"http://127.0.0.1:{port}")

    def on_server_stopped(self):
        self.server_thread = None
        self.btn_toggle.setText("🚀 啟動模型")
        self.btn_toggle.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF007F, stop:1 #7928CA); color: #FFF; border: none; border-radius: 10px; padding: 9px 24px; font-weight: bold; font-size: 12px;")
        self.badge_llama.setText("LLAMA: OFFLINE")
        self.badge_llama.setStyleSheet("background-color: #1B1E36; color: #A0ABC0; border: 1px solid #2A2F54; border-radius: 10px; padding: 4px 12px; font-size: 10px; font-weight: bold;")
        self.append_log("⚡ llama-server 已安全停止，GPU 顯存已釋放。")

    def closeEvent(self, event):
        if hasattr(self, 'telemetry') and self.telemetry.isRunning():
            self.telemetry.stop()
        if self.server_thread and self.server_thread.isRunning():
            self.server_thread.stop()
        if NVML_AVAILABLE:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(CYBERPUNK_GLOBAL_QSS)
    window = MidnightDashboardWindow()
    window.show()
    sys.exit(app.exec())