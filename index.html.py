
import sys
import os
import platform
import shutil
import subprocess
from collections import deque
from datetime import datetime

import psutil
import pyqtgraph as pg
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QVBoxLayout,
    QHBoxLayout, QGridLayout, QFrame, QProgressBar, QTabWidget
)


def gpu_stats():
    """Read NVIDIA GPU usage when nvidia-smi is available."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader,nounits"
            ],
            capture_output=True, text=True, timeout=2, check=True
        )
        values = result.stdout.strip().splitlines()[0].split(",")
        return {
            "usage": float(values[0].strip()),
            "used": float(values[1].strip()),
            "total": float(values[2].strip()),
            "temp": float(values[3].strip())
        }
    except Exception:
        return None


def temperatures():
    """Try common thermal sensor interfaces; may be unavailable on Windows."""
    readings = []
    try:
        base = "/sys/class/thermal"
        if os.path.isdir(base):
            for item in os.listdir(base):
                path = os.path.join(base, item, "temp")
                if os.path.isfile(path):
                    try:
                        value = float(open(path).read().strip())
                        if value > 1000:
                            value /= 1000
                        if 0 < value < 150:
                            readings.append(value)
                    except (ValueError, OSError):
                        pass
    except OSError:
        pass
    return max(readings) if readings else None


class MetricCard(QFrame):
    def __init__(self, name):
        super().__init__()
        self.setObjectName("metricCard")
        layout = QVBoxLayout(self)
        self.name = QLabel(name.upper())
        self.name.setObjectName("metricName")
        self.value = QLabel("--")
        self.value.setObjectName("metricValue")
        self.detail = QLabel("Waiting for data")
        self.detail.setObjectName("metricDetail")
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(7)
        layout.addWidget(self.name)
        layout.addWidget(self.value)
        layout.addWidget(self.detail)
        layout.addWidget(self.bar)

    def update_metric(self, value, detail, percent=None):
        self.value.setText(value)
        self.detail.setText(detail)
        self.bar.setValue(int(max(0, min(100, percent or 0))))


class Dashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Stylo Mini | System Health")
        self.resize(1100, 760)

        self.history = {
            "CPU": deque(maxlen=60),
            "Memory": deque(maxlen=60),
            "GPU": deque(maxlen=60)
        }

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(24, 20, 24, 20)
        root_layout.setSpacing(16)

        header = QHBoxLayout()
        heading = QVBoxLayout()
        title = QLabel("STYLO MINI")
        title.setObjectName("title")
        subtitle = QLabel("SYSTEM HEALTH MONITOR")
        subtitle.setObjectName("subtitle")
        heading.addWidget(title)
        heading.addWidget(subtitle)
        header.addLayout(heading)
        header.addStretch()

        self.status = QLabel("● INITIALIZING")
        self.status.setObjectName("status")
        header.addWidget(self.status, alignment=Qt.AlignmentFlag.AlignRight)
        root_layout.addLayout(header)

        self.tabs = QTabWidget()
        root_layout.addWidget(self.tabs)

        overview = QWidget()
        overview_layout = QVBoxLayout(overview)
        overview_layout.setSpacing(14)

        grid = QGridLayout()
        grid.setSpacing(12)
        self.cards = {
            "CPU": MetricCard("CPU usage"),
            "Memory": MetricCard("RAM usage"),
            "Disk": MetricCard("Storage usage"),
            "GPU": MetricCard("NVIDIA GPU"),
            "Temperature": MetricCard("Temperature"),
            "Swap": MetricCard("Virtual memory")
        }
        positions = [
            ("CPU", 0, 0), ("Memory", 0, 1), ("GPU", 0, 2),
            ("Disk", 1, 0), ("Temperature", 1, 1), ("Swap", 1, 2)
        ]
        for key, row, col in positions:
            grid.addWidget(self.cards[key], row, col)
        overview_layout.addLayout(grid)

        self.chart = pg.PlotWidget()
        self.chart.setBackground("#111827")
        self.chart.setTitle("LIVE RESOURCE UTILIZATION", color="#e5e7eb")
        self.chart.setLabel("left", "Usage", units="%")
        self.chart.setLabel("bottom", "Recent samples")
        self.chart.setYRange(0, 100)
        self.chart.showGrid(x=True, y=True, alpha=0.2)
        self.chart.addLegend()
        self.lines = {
            "CPU": self.chart.plot(pen=pg.mkPen("#60a5fa", width=2),
                                   name="CPU"),
            "Memory": self.chart.plot(pen=pg.mkPen("#34d399", width=2),
                                      name="RAM"),
            "GPU": self.chart.plot(pen=pg.mkPen("#fbbf24", width=2),
                                   name="GPU")
        }
        overview_layout.addWidget(self.chart, 1)
        self.tabs.addTab(overview, "Overview")

        info_page = QWidget()
        info_layout = QVBoxLayout(info_page)
        info_title = QLabel("DEVICE INFORMATION")
        info_title.setObjectName("sectionTitle")
        info_layout.addWidget(info_title)

        disk = shutil.disk_usage(os.path.abspath(os.sep))
        info_text = (
            f"Operating system: {platform.platform()}\n"
            f"Device: {platform.node()}\n"
            f"Architecture: {platform.machine()}\n"
            f"Processor: {platform.processor() or 'Not reported'}\n"
            f"Logical CPU cores: {psutil.cpu_count(logical=True)}\n"
            f"Physical CPU cores: {psutil.cpu_count(logical=False)}\n"
            f"Total RAM: {psutil.virtual_memory().total / (1024**3):.2f} GB\n"
            f"System drive capacity: {disk.total / (1024**3):.2f} GB\n"
            f"Python: {platform.python_version()}\n"
            f"Refresh interval: 2 seconds"
        )
        self.info = QLabel(info_text)
        self.info.setObjectName("infoText")
        self.info.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        info_layout.addWidget(self.info)
        info_layout.addStretch()
        self.tabs.addTab(info_page, "Device Info")

        self.footer = QLabel("Starting monitor...")
        self.footer.setObjectName("footer")
        root_layout.addWidget(self.footer)
        self.setCentralWidget(root)

        self.setStyleSheet("""
            QMainWindow, QWidget {
                background: #0b1120;
                color: #e5e7eb;
                font-family: Segoe UI, Arial;
                font-size: 13px;
            }
            QLabel#title {
                font-size: 27px;
                font-weight: 700;
                color: #f9fafb;
            }
            QLabel#subtitle {
                color: #94a3b8;
                letter-spacing: 2px;
                font-size: 11px;
            }
            QLabel#status { color: #34d399; font-weight: 600; }
            QFrame#metricCard {
                background: #151e30;
                border: 1px solid #263449;
                border-radius: 12px;
            }
            QLabel#metricName {
                color: #94a3b8;
                font-size: 11px;
                font-weight: 600;
            }
            QLabel#metricValue {
                color: #f9fafb;
                font-size: 27px;
                font-weight: 700;
            }
            QLabel#metricDetail { color: #9ca3af; font-size: 11px; }
            QProgressBar {
                background: #263449;
                border: none;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background: #60a5fa;
                border-radius: 3px;
            }
            QTabWidget::pane {
                border: 1px solid #263449;
                border-radius: 8px;
            }
            QTabBar::tab {
                background: #151e30;
                padding: 10px 20px;
                margin-right: 4px;
                color: #9ca3af;
            }
            QTabBar::tab:selected {
                color: #60a5fa;
                border-bottom: 2px solid #60a5fa;
            }
            QLabel#sectionTitle {
                font-size: 20px;
                font-weight: 700;
            }
            QLabel#infoText {
                font-size: 15px;
                line-height: 1.7;
                padding: 12px;
            }
            QLabel#footer { color: #64748b; font-size: 11px; }
        """)

        # Initialize CPU sampling before the timer starts.
        psutil.cpu_percent(interval=None)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(2000)
        self.refresh()

    def refresh(self):
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk = psutil.disk_usage(os.path.abspath(os.sep))
        gpu = gpu_stats()
        temp = temperatures()

        self.cards["CPU"].update_metric(
            f"{cpu:.0f}%", f"{psutil.cpu_count()} logical cores", cpu
        )
        self.cards["Memory"].update_metric(
            f"{mem.percent:.0f}%",
            f"{mem.used / (1024**3):.1f} / {mem.total / (1024**3):.1f} GB",
            mem.percent
        )
        self.cards["Disk"].update_metric(
            f"{disk.percent:.0f}%",
            f"{disk.used / (1024**3):.1f} / {disk.total / (1024**3):.1f} GB",
            disk.percent
        )
        self.cards["Swap"].update_metric(
            f"{swap.percent:.0f}%",
            f"{swap.used / (1024**3):.2f} / {swap.total / (1024**3):.2f} GB",
            swap.percent
        )

        if gpu:
            self.cards["GPU"].update_metric(
                f"{gpu['usage']:.0f}%",
                f"VRAM {gpu['used']:.0f} / {gpu['total']:.0f} MiB",
                gpu["usage"]
            )
            gpu_usage = gpu["usage"]
            gpu_text = f"NVIDIA GPU temperature: {gpu['temp']:.0f} °C"
        else:
            self.cards["GPU"].update_metric(
                "N/A", "NVIDIA telemetry unavailable", 0
            )
            gpu_usage = 0
            gpu_text = "NVIDIA GPU telemetry unavailable"

        if temp is not None:
            self.cards["Temperature"].update_metric(
                f"{temp:.0f} °C", "Highest detected thermal sensor", 0
            )
            temp_text = f"Thermal sensor: {temp:.0f} °C"
        elif gpu:
            self.cards["Temperature"].update_metric(
                f"{gpu['temp']:.0f} °C", "NVIDIA GPU temperature", 0
            )
            temp_text = gpu_text
        else:
            self.cards["Temperature"].update_metric(
                "N/A", "Sensor unavailable on this system", 0
            )
            temp_text = "Temperature sensor unavailable"

        self.history["CPU"].append(cpu)
        self.history["Memory"].append(mem.percent)
        self.history["GPU"].append(gpu_usage)

        for key, values in self.history.items():
            self.lines[key].setData(list(values))

        warnings = []
        if cpu >= 90:
            warnings.append("High CPU usage")
        if mem.percent >= 90:
            warnings.append("High RAM usage")
        if disk.percent >= 95:
            warnings.append("Low disk space")

        if warnings:
            self.status.setText("● WARNING")
            self.status.setStyleSheet("color: #f87171; font-weight: 700;")
            status_text = " | ".join(warnings)
        else:
            self.status.setText("● SYSTEM HEALTHY")
            self.status.setStyleSheet("color: #34d399; font-weight: 700;")
            status_text = "No resource thresholds exceeded"

        self.footer.setText(
            f"Updated {datetime.now().strftime('%H:%M:%S')}  |  "
            f"{status_text}  |  {temp_text}"
        )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = Dashboard()
    window.show()
    sys.exit(app.exec())
