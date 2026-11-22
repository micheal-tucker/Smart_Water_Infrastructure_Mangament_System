"""SWIMS: Smart Water Infrastructure Management System.

Python + PyQt6 desktop application for community water operations.
Set SWIMS_DATABASE_URL to connect to PostgreSQL. Without it, the app opens
with clearly labelled sample data so the interface can be explored offline.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QFileDialog, QSizePolicy,
    QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
    QHeaderView, QGraphicsDropShadowEffect,
)


# ------------------------------ Domain model ------------------------------
class WaterAsset(ABC):
    """Abstract base class for infrastructure assets."""

    def __init__(self, asset_id: int, name: str, community: str, status: str):
        self._asset_id = asset_id
        self._name = name
        self._community = community
        self._status = status

    @property
    def asset_id(self) -> int:
        return self._asset_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def community(self) -> str:
        return self._community

    @property
    def status(self) -> str:
        return self._status

    @status.setter
    def status(self, value: str) -> None:
        self._status = value

    @abstractmethod
    def summary(self) -> str:
        """Return a user-facing description of this asset."""


class WaterTank(WaterAsset):
    """Tank object; its status and fill level drive the UI indicators."""

    def __init__(self, asset_id: int, code: str, community: str, capacity: int,
                 level: int, flow: float, valve: str, status: str,
                 updated: str = "Just now"):
        super().__init__(asset_id, code, community, status)
        self._capacity, self._level = capacity, level
        self.flow, self.valve, self.updated = flow, valve, updated

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def level(self) -> int:
        return self._level

    @level.setter
    def level(self, value: int) -> None:
        self._level = max(0, min(value, self._capacity))

    @property
    def percentage(self) -> int:
        return round(self._level * 100 / self._capacity) if self._capacity else 0

    def summary(self) -> str:
        return f"{self.name} · {self.community} · {self.percentage}% full"


class Sensor(WaterAsset):
    def __init__(self, asset_id: int, name: str, community: str, reading: str,
                 status: str = "Online"):
        super().__init__(asset_id, name, community, status)
        self.reading = reading

    def summary(self) -> str:
        return f"{self.name}: {self.reading} ({self.status})"


class Equipment(WaterAsset):
    def __init__(self, asset_id: int, name: str, community: str, kind: str,
                 installed: str, status: str):
        super().__init__(asset_id, name, community, status)
        self.kind, self.installed = kind, installed

    def summary(self) -> str:
        return f"{self.kind} · {self.name} · {self.status}"


@dataclass
class Alert:
    alert_id: int
    title: str
    tank: str
    severity: str
    time: str
    detail: str
    resolved: bool = False


@dataclass
class Community:
    community_id: int
    name: str
    location: str
    tanks: int
    households: int


RECORD_SCHEMAS = {
    "sensors": ("Sensor ID", "Type", "Tank / location", "Current reading", "Status"),
    "transactions": ("Reference", "Tank", "Type", "Volume (L)", "Date & time"),
    "equipment": ("Asset ID", "Equipment name", "Type / location", "Status", "Installed"),
    "maintenance": ("Task", "Asset", "Technician", "Status", "Date"),
    "technicians": ("Name", "Phone", "Email", "Specialization", "Assignment"),
}

SEED_RECORDS = {
    "sensors": [
        ["SEN-UL-001", "Ultrasonic level", "TNK-001 · Brookside", "2.04 m", "Online"],
        ["SEN-FL-002", "Flow meter", "TNK-002 · Hillview", "9.2 L/min", "Online"],
        ["SEN-UL-003", "Ultrasonic level", "TNK-003 · Riverside", "0.83 m", "Warning"],
    ],
    "transactions": [
        ["TRX-2081", "TNK-001", "Inflow", "2400", "Today · 09:42"],
        ["TRX-2080", "TNK-002", "Usage", "840", "Today · 09:30"],
    ],
    "equipment": [
        ["PMP-001", "Booster pump", "TNK-001 · Brookside", "Operational", "12 Jun 2025"],
        ["VLV-003", "Control valve", "TNK-003 · Riverside", "Maintenance required", "08 Mar 2025"],
    ],
    "maintenance": [
        ["Pump inspection", "PMP-001 · Brookside", "Joseph Kamara", "In progress", "Today"],
        ["Valve replacement", "VLV-003 · Riverside", "Mariama Sesay", "Scheduled", "24 Nov 2026"],
    ],
    "technicians": [
        ["Joseph Kamara", "+232 76 555 018", "j.kamara@swims.gov.sl", "Pumps & motors", "2 active tasks"],
        ["Mariama Sesay", "+232 77 210 044", "m.sesay@swims.gov.sl", "Valves & controls", "1 active task"],
    ],
}


# ----------------------------- Data repository ----------------------------
class AssetRepository(ABC):
    """Storage interface. GUI works against this contract (abstraction)."""

    @abstractmethod
    def tanks(self) -> list[WaterTank]: ...

    @abstractmethod
    def communities(self) -> list[Community]: ...

    @abstractmethod
    def alerts(self) -> list[Alert]: ...

    @abstractmethod
    def save_tank(self, tank: WaterTank) -> WaterTank: ...

    @abstractmethod
    def delete_tank(self, tank_id: int) -> None: ...

    @abstractmethod
    def save_community(self, community: Community) -> Community: ...

    @abstractmethod
    def delete_community(self, community_id: int) -> None: ...

    @abstractmethod
    def resolve_alert(self, alert_id: int) -> None: ...

    @abstractmethod
    def records(self, category: str) -> list[tuple[int, list[str]]]: ...

    @abstractmethod
    def save_record(self, category: str, record_id: int, fields: list[str]) -> int: ...

    @abstractmethod
    def delete_record(self, category: str, record_id: int) -> None: ...


class DemoRepository(AssetRepository):
    """Small in-memory dataset for an immediate, offline demo."""

    def __init__(self):
        self._tanks = [
            WaterTank(1, "TNK-001", "Brookside", 25000, 20400, 18.4, "Open", "Normal", "1 min ago"),
            WaterTank(2, "TNK-002", "Hillview", 18000, 6840, 9.2, "Open", "Warning", "2 min ago"),
            WaterTank(3, "TNK-003", "Riverside", 32000, 8320, 0.0, "Closed", "Critical", "4 min ago"),
            WaterTank(4, "TNK-004", "Brookside", 22000, 18700, 14.1, "Open", "Normal", "5 min ago"),
            WaterTank(5, "TNK-005", "Eastbank", 15000, 12000, 11.8, "Open", "Normal", "8 min ago"),
        ]
        self._communities = [
            Community(1, "Brookside", "Western Area · Freetown", 2, 1240),
            Community(2, "Hillview", "Waterloo · Western Area", 1, 860),
            Community(3, "Riverside", "Bo District", 1, 1540),
            Community(4, "Eastbank", "Kenema District", 1, 690),
        ]
        self._alerts = [
            Alert(1, "Critical water level", "TNK-003 · Riverside", "Critical", "4 min ago", "Tank is at 26% capacity. Inspect source supply and pump."),
            Alert(2, "Low water level", "TNK-002 · Hillview", "Warning", "18 min ago", "Water level has fallen below the 40% operating threshold."),
            Alert(3, "Flow anomaly detected", "TNK-001 · Brookside", "Info", "42 min ago", "Flow varies from the expected morning baseline."),
        ]
        self._records = {key: [[i + 1, list(row)] for i, row in enumerate(rows)]
                         for key, rows in SEED_RECORDS.items()}
        self._next_record_id = {key: len(rows) + 1 for key, rows in SEED_RECORDS.items()}

    def tanks(self) -> list[WaterTank]: return self._tanks
    def communities(self) -> list[Community]: return self._communities
    def alerts(self) -> list[Alert]: return self._alerts

    def save_tank(self, tank: WaterTank) -> WaterTank:
        for i, old in enumerate(self._tanks):
            if old.asset_id == tank.asset_id:
                self._tanks[i] = tank
                return tank
        tank._asset_id = max([t.asset_id for t in self._tanks], default=0) + 1
        self._tanks.append(tank)
        return tank

    def delete_tank(self, tank_id: int) -> None:
        self._tanks = [tank for tank in self._tanks if tank.asset_id != tank_id]

    def save_community(self, community: Community) -> Community:
        for index, current in enumerate(self._communities):
            if current.community_id == community.community_id and community.community_id:
                previous_name = current.name
                self._communities[index] = community
                for tank in self._tanks:
                    if tank.community == previous_name:
                        tank._community = community.name
                return community
        community.community_id = max((item.community_id for item in self._communities), default=0) + 1
        self._communities.append(community)
        return community

    def delete_community(self, community_id: int) -> None:
        deleted = next((item for item in self._communities if item.community_id == community_id), None)
        self._communities = [item for item in self._communities if item.community_id != community_id]
        if deleted:
            for tank in self._tanks:
                if tank.community == deleted.name:
                    tank._community = "Unassigned"

    def resolve_alert(self, alert_id: int) -> None:
        for alert in self._alerts:
            if alert.alert_id == alert_id:
                alert.resolved = True

    def records(self, category: str) -> list[tuple[int, list[str]]]:
        return [(record_id, list(fields)) for record_id, fields in self._records.get(category, [])]

    def save_record(self, category: str, record_id: int, fields: list[str]) -> int:
        rows = self._records.setdefault(category, [])
        for index, (current_id, _) in enumerate(rows):
            if current_id == record_id:
                rows[index] = [record_id, list(fields)]
                return record_id
        new_id = self._next_record_id.get(category, 1)
        self._next_record_id[category] = new_id + 1
        rows.append([new_id, list(fields)])
        return new_id

    def delete_record(self, category: str, record_id: int) -> None:
        self._records[category] = [row for row in self._records.get(category, []) if row[0] != record_id]


class PostgresRepository(AssetRepository):
    """PostgreSQL implementation. Accepts a DSN or standard connection fields."""

    def __init__(self, dsn: str | dict[str, object]):
        try:
            import psycopg2
        except ImportError as exc:
            raise RuntimeError("Install dependencies with: pip install -r requirements.txt") from exc
        self._db = psycopg2.connect(dsn) if isinstance(dsn,str) else psycopg2.connect(**dsn)
        self._db.autocommit = True
        self._setup()

    def _setup(self) -> None:
        with self._db.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS communities (
                id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL, location TEXT NOT NULL,
                households INTEGER NOT NULL DEFAULT 0)""")
            cur.execute("""CREATE TABLE IF NOT EXISTS tanks (
                id SERIAL PRIMARY KEY, code TEXT UNIQUE NOT NULL,
                community_id INTEGER REFERENCES communities(id) ON DELETE SET NULL,
                capacity_l INTEGER NOT NULL CHECK(capacity_l > 0), level_l INTEGER NOT NULL DEFAULT 0,
                flow_lpm NUMERIC(8,2) NOT NULL DEFAULT 0, valve TEXT NOT NULL DEFAULT 'Open',
                status TEXT NOT NULL DEFAULT 'Normal', updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            cur.execute("""CREATE TABLE IF NOT EXISTS alerts (
                id SERIAL PRIMARY KEY, title TEXT NOT NULL, tank_code TEXT NOT NULL,
                severity TEXT NOT NULL, detail TEXT NOT NULL, resolved BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            cur.execute("""CREATE TABLE IF NOT EXISTS swims_records (
                id SERIAL PRIMARY KEY, category TEXT NOT NULL,
                data JSONB NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            cur.execute("SELECT COUNT(*) FROM communities")
            if cur.fetchone()[0] == 0:
                cur.execute("""INSERT INTO communities(name,location,households) VALUES
                    ('Brookside','Western Area · Freetown',1240),
                    ('Hillview','Waterloo · Western Area',860),
                    ('Riverside','Bo District',1540),
                    ('Eastbank','Kenema District',690)""")

    def tanks(self) -> list[WaterTank]:
        with self._db.cursor() as cur:
            cur.execute("""SELECT t.id,t.code,COALESCE(c.name,'Unassigned'),t.capacity_l,t.level_l,
                t.flow_lpm,t.valve,t.status,t.updated_at FROM tanks t LEFT JOIN communities c ON c.id=t.community_id ORDER BY t.code""")
            return [WaterTank(i, code, community, capacity, level, float(flow), valve, status,
                              stamp.strftime('%H:%M') if stamp else '—')
                    for i, code, community, capacity, level, flow, valve, status, stamp in cur.fetchall()]

    def communities(self) -> list[Community]:
        with self._db.cursor() as cur:
            cur.execute("""SELECT c.id,c.name,c.location,COUNT(t.id),c.households FROM communities c
                LEFT JOIN tanks t ON t.community_id=c.id GROUP BY c.id ORDER BY c.name""")
            return [Community(*row) for row in cur.fetchall()]

    def alerts(self) -> list[Alert]:
        with self._db.cursor() as cur:
            cur.execute("SELECT id,title,tank_code,severity,created_at,detail,resolved FROM alerts ORDER BY created_at DESC")
            return [Alert(i, title, tank, severity, stamp.strftime('%H:%M'), detail, resolved)
                    for i, title, tank, severity, stamp, detail, resolved in cur.fetchall()]

    def save_tank(self, tank: WaterTank) -> WaterTank:
        with self._db.cursor() as cur:
            cur.execute("SELECT id FROM communities WHERE name=%s", (tank.community,))
            row = cur.fetchone()
            community_id = row[0] if row else None
            if tank.asset_id:
                cur.execute("""UPDATE tanks SET code=%s,community_id=%s,capacity_l=%s,level_l=%s,
                    flow_lpm=%s,valve=%s,status=%s,updated_at=NOW() WHERE id=%s""",
                    (tank.name, community_id, tank.capacity, tank.level, tank.flow, tank.valve, tank.status, tank.asset_id))
                if cur.rowcount:
                    return tank
            cur.execute("""INSERT INTO tanks(code,community_id,capacity_l,level_l,flow_lpm,valve,status)
                VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (tank.name, community_id, tank.capacity, tank.level, tank.flow, tank.valve, tank.status))
            tank._asset_id = cur.fetchone()[0]
        return tank

    def delete_tank(self, tank_id: int) -> None:
        with self._db.cursor() as cur: cur.execute("DELETE FROM tanks WHERE id=%s", (tank_id,))

    def save_community(self, community: Community) -> Community:
        with self._db.cursor() as cur:
            if community.community_id:
                cur.execute("UPDATE communities SET name=%s,location=%s,households=%s WHERE id=%s",
                            (community.name, community.location, community.households, community.community_id))
                if cur.rowcount:
                    return community
            cur.execute("INSERT INTO communities(name,location,households) VALUES(%s,%s,%s) RETURNING id",
                        (community.name, community.location, community.households))
            community.community_id = cur.fetchone()[0]
        return community

    def delete_community(self, community_id: int) -> None:
        with self._db.cursor() as cur: cur.execute("DELETE FROM communities WHERE id=%s", (community_id,))

    def resolve_alert(self, alert_id: int) -> None:
        with self._db.cursor() as cur: cur.execute("UPDATE alerts SET resolved=TRUE WHERE id=%s", (alert_id,))

    def records(self, category: str) -> list[tuple[int, list[str]]]:
        with self._db.cursor() as cur:
            cur.execute("SELECT id,data FROM swims_records WHERE category=%s ORDER BY id", (category,))
            return [(record_id, [str(value) for value in data]) for record_id, data in cur.fetchall()]

    def save_record(self, category: str, record_id: int, fields: list[str]) -> int:
        from psycopg2.extras import Json
        with self._db.cursor() as cur:
            if record_id:
                cur.execute("UPDATE swims_records SET data=%s,updated_at=NOW() WHERE category=%s AND id=%s",
                            (Json(fields), category, record_id))
                if cur.rowcount:
                    return record_id
            cur.execute("INSERT INTO swims_records(category,data) VALUES(%s,%s) RETURNING id",
                        (category, Json(fields)))
            return cur.fetchone()[0]

    def delete_record(self, category: str, record_id: int) -> None:
        with self._db.cursor() as cur:
            cur.execute("DELETE FROM swims_records WHERE category=%s AND id=%s", (category, record_id))


# --------------------------------- Styling ---------------------------------
PALETTE = {
    "navy": "#102A43", "ink": "#183B56", "muted": "#8295A6", "blue": "#1687D9",
    "aqua": "#30C7C9", "pale": "#EAF7FB", "canvas": "#F4F8FB", "line": "#E7EEF3",
    "green": "#20A879", "orange": "#E59A27", "red": "#E05B63", "white": "#FFFFFF",
}

APP_STYLE = f"""
QWidget {{ font-family: 'Segoe UI', 'Inter', sans-serif; color: {PALETTE['ink']}; font-size: 13px; }}
QMainWindow, QDialog {{ background: {PALETTE['canvas']}; }}
QFrame#sidebar {{ background: {PALETTE['navy']}; border: none; }}
QFrame#card {{ background: white; border: 1px solid {PALETTE['line']}; border-radius: 14px; }}
QLabel#muted {{ color: {PALETTE['muted']}; }}
QLabel#pageTitle {{ color: {PALETTE['navy']}; font-size: 25px; font-weight: 700; }}
QLabel#sectionTitle {{ color: {PALETTE['navy']}; font-size: 15px; font-weight: 700; }}
QPushButton {{ background: white; border: 1px solid {PALETTE['line']}; border-radius: 9px; padding: 9px 14px; font-weight: 600; }}
QPushButton:hover {{ border-color: {PALETTE['blue']}; color: {PALETTE['blue']}; }}
QPushButton#primary {{ background: {PALETTE['blue']}; color: white; border: 0; padding: 10px 16px; }}
QPushButton#primary:hover {{ background: #0874C2; color: white; }}
QPushButton#nav {{ background: transparent; color: #B9CAD8; border: 0; border-radius: 9px; text-align: left; padding: 12px 14px; font-size: 13px; }}
QPushButton#nav:hover, QPushButton#nav[selected="true"] {{ background: #23445E; color: white; }}
QLineEdit, QComboBox {{ background: white; border: 1px solid {PALETTE['line']}; border-radius: 9px; padding: 10px 11px; min-height: 18px; }}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {PALETTE['blue']}; }}
QTableWidget {{ background: white; border: none; gridline-color: {PALETTE['line']}; border-radius: 12px; selection-background-color: #E9F5FC; selection-color: {PALETTE['ink']}; }}
QTableWidget::item {{ padding: 5px 10px; border-bottom: 1px solid #F0F4F7; }}
QTableWidget::item:alternate {{ background: #FAFCFD; }}
QTableWidget::item {{ padding: 5px 10px; border-bottom: 1px solid #F0F4F7; }}
QTableWidget::item:alternate {{ background: #FAFCFD; }}
QHeaderView::section {{ background: #F7FAFC; color: {PALETTE['muted']}; border: none; border-bottom: 1px solid {PALETTE['line']}; padding: 11px; font-weight: 600; }}
QCheckBox {{ spacing: 10px; padding: 7px 2px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; }}
QScrollArea {{ border: none; background: transparent; }}
"""

DARK_STYLE = APP_STYLE + f"""
QMainWindow, QDialog, QWidget {{ background: #101D29; color: #E6EEF5; }}
QFrame#card {{ background: #182A39; border: 1px solid #294052; }}
QLabel#pageTitle, QLabel#sectionTitle {{ color: #F0F6FA; }}
QLabel#muted {{ color: #9DB0BF; }}
QLineEdit, QComboBox, QTableWidget {{ background: #182A39; color: #E6EEF5; border-color: #294052; }}
QHeaderView::section {{ background: #203444; color: #B8C8D4; border-color: #294052; }}
QPushButton {{ background: #203444; color: #E6EEF5; border-color: #294052; }}
QPushButton#primary {{ background: {PALETTE['blue']}; color: white; }}
QTableWidget {{ selection-background-color: #254966; selection-color: white; }}
QTableWidget::item {{ border-bottom-color: #223746; }}
QTableWidget::item:alternate {{ background: #152533; }}
"""


def card() -> QFrame:
    frame = QFrame(); frame.setObjectName("card")
    shadow=QGraphicsDropShadowEffect(frame); shadow.setBlurRadius(18); shadow.setOffset(0,3); shadow.setColor(QColor(16,42,67,18)); frame.setGraphicsEffect(shadow)
    return frame


def label(text: str, name: str = "") -> QLabel:
    result = QLabel(text)
    if name: result.setObjectName(name)
    return result


def section_heading(title: str, subtitle: str = "") -> QWidget:
    box = QWidget(); lay = QVBoxLayout(box); lay.setContentsMargins(0, 0, 0, 2); lay.setSpacing(3)
    lay.addWidget(label(title, "sectionTitle"))
    if subtitle: lay.addWidget(label(subtitle, "muted"))
    return box


def make_button(text: str, primary: bool = False) -> QPushButton:
    button = QPushButton(text)
    if primary: button.setObjectName("primary")
    return button


class DonutChart(QWidget):
    """Compact, native Qt chart; no web view or non-Python UI layer."""
    def __init__(self):
        super().__init__(); self.setMinimumSize(150, 150); self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding); self.tanks=[]
    def set_tanks(self,tanks): self.tanks=list(tanks); self.update()

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(18, 18, -18, -18)
        p.setPen(QPen(QColor("#EAF0F4"), 16, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)); p.drawArc(rect, 0, 360 * 16)
        counts=[sum(t.status==status for t in self.tanks) for status in ("Normal","Warning","Critical")]
        total=max(sum(counts),1); segments=[(round(count/total*360),color) for count,color in zip(counts,(PALETTE["green"],PALETTE["orange"],PALETTE["red"]))]
        start = 90 * 16
        for degrees, color in segments:
            p.setPen(QPen(QColor(color), 16, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)); p.drawArc(rect, start, -degrees * 16); start -= degrees * 16
        p.setPen(QColor(PALETTE["navy"])); f = p.font(); f.setPointSize(22); f.setBold(True); p.setFont(f)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, str(len(self.tanks)))
        f.setPointSize(9); f.setBold(False); p.setFont(f); p.setPen(QColor(PALETTE["muted"]))
        p.drawText(self.rect().adjusted(0, 30, 0, 0), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, "Tanks")


class UsageChart(QWidget):
    def __init__(self): super().__init__(); self.setMinimumHeight(160); self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing); r = self.rect().adjusted(32, 12, -12, -28)
        vals = [42, 52, 44, 68, 56, 77, 60, 82, 71, 91, 76, 66]
        for tick in range(4):
            y = r.top() + tick * r.height() / 3
            p.setPen(QPen(QColor("#EAF0F4"), 1)); p.drawLine(int(r.left()), int(y), int(r.right()), int(y))
        points = []
        for i, val in enumerate(vals):
            x = r.left() + i * r.width() / (len(vals)-1); y = r.bottom() - val * r.height()/100
            points.append((int(x), int(y)))
        p.setPen(QPen(QColor(PALETTE["blue"]), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        for a, b in zip(points, points[1:]): p.drawLine(*a, *b)
        p.setBrush(QColor(PALETTE["blue"])); p.setPen(Qt.PenStyle.NoPen)
        for x, y in points: p.drawEllipse(x-3, y-3, 6, 6)
        p.setPen(QColor(PALETTE["muted"])); f = p.font(); f.setPointSize(8); p.setFont(f)
        for i, t in enumerate(["06:00", "09:00", "12:00", "15:00", "18:00", "Now"]):
            x = r.left() + i*r.width()/5; p.drawText(int(x-18), r.bottom()+20, t)


class TankDialog(QDialog):
    def __init__(self, communities: list[Community], tank: Optional[WaterTank] = None):
        super().__init__(); self.setWindowTitle("Tank details"); self.setMinimumWidth(400); self.tank_id = tank.asset_id if tank else 0
        layout = QVBoxLayout(self); layout.setSpacing(15); layout.addWidget(label("Tank information", "sectionTitle"))
        form = QFormLayout(); form.setSpacing(12)
        self.code = QLineEdit(tank.name if tank else ""); self.code.setPlaceholderText("e.g. TNK-006")
        self.community = QComboBox(); self.community.addItems([c.name for c in communities] or ["Unassigned"])
        self.capacity = QLineEdit(str(tank.capacity if tank else 20000)); self.level = QLineEdit(str(tank.level if tank else 0))
        self.flow = QLineEdit(str(tank.flow if tank else 0)); self.valve = QComboBox(); self.valve.addItems(["Open", "Closed"])
        self.status = QComboBox(); self.status.addItems(["Normal", "Warning", "Critical"])
        if tank:
            self.community.setCurrentText(tank.community); self.valve.setCurrentText(tank.valve); self.status.setCurrentText(tank.status)
        for title, widget in [("Tank code",self.code),("Community",self.community),("Capacity (L)",self.capacity),("Current level (L)",self.level),("Flow rate (L/min)",self.flow),("Valve",self.valve),("Status",self.status)]: form.addRow(title,widget)
        layout.addLayout(form); buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel|QDialogButtonBox.StandardButton.Save)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def value(self) -> WaterTank:
        code = self.code.text().strip()
        if not code: raise ValueError("Enter a tank code.")
        capacity, level, flow = int(self.capacity.text()), int(self.level.text()), float(self.flow.text())
        if capacity <= 0 or not 0 <= level <= capacity: raise ValueError("Capacity must be positive and water level must be within capacity.")
        if flow < 0: raise ValueError("Flow rate cannot be negative.")
        return WaterTank(self.tank_id, code, self.community.currentText(), capacity, level, flow,
                         self.valve.currentText(), self.status.currentText())


class LoginDialog(QDialog):
    """Simple operator entry screen for the desktop prototype."""
    def __init__(self):
        super().__init__(); self.setWindowTitle("Sign in · SWIMS"); self.setFixedSize(440, 570)
        self.setStyleSheet("QDialog{background:#F4F8FB;} QLabel{color:#183B56;} QLineEdit{padding:13px;border:1px solid #E1EAF0;border-radius:10px;background:white;} QPushButton{padding:13px;border-radius:10px;}")
        root=QVBoxLayout(self); root.setContentsMargins(42,34,42,30); root.setSpacing(13)
        brand=QHBoxLayout(); icon=QLabel("≈"); icon.setAlignment(Qt.AlignmentFlag.AlignCenter); icon.setFixedSize(48,48); icon.setStyleSheet("background:#1687D9;color:white;border-radius:15px;font-size:34px;font-weight:bold;"); brand.addWidget(icon)
        name=QVBoxLayout(); t=QLabel("SWIMS"); t.setStyleSheet("font-size:21px;font-weight:800;letter-spacing:1px;color:#102A43;"); name.addWidget(t); sub=QLabel("SMART WATER INFRASTRUCTURE"); sub.setStyleSheet("font-size:9px;letter-spacing:1px;color:#8295A6;"); name.addWidget(sub); brand.addLayout(name); brand.addStretch(); root.addLayout(brand); root.addSpacing(18)
        art=QFrame(); art.setFixedHeight(142); art.setStyleSheet("background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #DDF5F7,stop:1 #DCEEFF);border-radius:18px;"); artlay=QVBoxLayout(art); artlay.addStretch(); wave=QLabel("     〰      〰      〰"); wave.setStyleSheet("font-size:26px;color:#1687D9;"); artlay.addWidget(wave); artlay.addWidget(QLabel("      Clean water. Connected communities.")); artlay.addStretch(); root.addWidget(art)
        welcome=QLabel("Welcome back"); welcome.setStyleSheet("font-size:22px;font-weight:700;color:#102A43;"); root.addWidget(welcome); root.addWidget(QLabel("Sign in to your water operations workspace."))
        root.addSpacing(5); root.addWidget(QLabel("Work email")); self.email=QLineEdit(); self.email.setPlaceholderText("name@waterutility.org"); self.email.setText("amina@swims.gov.sl"); root.addWidget(self.email)
        root.addWidget(QLabel("Password")); self.password=QLineEdit(); self.password.setPlaceholderText("Enter your password"); self.password.setEchoMode(QLineEdit.EchoMode.Password); self.password.setText("operator"); root.addWidget(self.password)
        forgot=QLabel("Forgot password?"); forgot.setAlignment(Qt.AlignmentFlag.AlignRight); forgot.setStyleSheet("color:#1687D9;font-weight:600;"); root.addWidget(forgot); root.addStretch()
        button=QPushButton("Sign in to SWIMS  →"); button.setStyleSheet("background:#1687D9;color:white;font-weight:700;"); button.clicked.connect(self._sign_in); root.addWidget(button)
        root.addWidget(QLabel("Secure access for authorized utility staff"),0,Qt.AlignmentFlag.AlignCenter)
    def _sign_in(self):
        if not self.email.text().strip() or not self.password.text():
            QMessageBox.warning(self,"Sign in required","Enter your email and password to continue."); return
        self.accept()


# ---------------------------------- Pages ----------------------------------
class DashboardPage(QWidget):
    def __init__(self, repo: AssetRepository):
        super().__init__(); self.repo = repo
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(18)
        top = QHBoxLayout(); top.addWidget(section_heading("Good morning, Amina 👋", "Here’s what’s happening across your water network.")); top.addStretch()
        live = QLabel("●  LIVE SYSTEM"); live.setStyleSheet("color:#14835F;background:#E5F6EF;border-radius:10px;padding:8px 12px;font-size:11px;font-weight:700;"); top.addWidget(live,0,Qt.AlignmentFlag.AlignTop); root.addLayout(top)
        self.metrics = QGridLayout(); self.metrics.setSpacing(12); self.metrics.setContentsMargins(0,0,0,0); root.addLayout(self.metrics); self._metric_cards=[]
        specs = [("Communities", "communities", "◈", PALETTE["blue"]),("Water tanks", "tanks", "▤", PALETTE["aqua"]),("Water stored", "water", "≈", PALETTE["green"]),("Active alerts", "alerts", "!", PALETTE["orange"])]
        for title, key, icon, color in specs:
            frame=card(); lay=QVBoxLayout(frame); lay.setContentsMargins(16,14,16,14); lay.setSpacing(8)
            head=QHBoxLayout(); head.addWidget(label(title,"muted")); head.addStretch(); ico=label(icon); ico.setStyleSheet(f"color:{color};font-size:19px;font-weight:700;"); head.addWidget(ico); lay.addLayout(head)
            val=label("—"); val.setStyleSheet("font-size:27px;font-weight:700;color:#102A43;"); lay.addWidget(val)
            foot=label("Across your service area"); foot.setStyleSheet("font-size:11px;color:#8295A6;"); lay.addWidget(foot)
            self.metrics.addWidget(frame,0,len(self._metric_cards)); self._metric_cards.append((val,key))
        for column in range(len(specs)): self.metrics.setColumnStretch(column,1)
        middle=QHBoxLayout(); middle.setSpacing(14)
        level_card=card(); ll=QVBoxLayout(level_card); ll.setContentsMargins(18,16,18,16); ll.setSpacing(10)
        ll.addWidget(section_heading("Tank level overview", "Live capacity across connected tanks"))
        chartrow=QHBoxLayout(); self.level_chart=DonutChart(); chartrow.addWidget(self.level_chart,2); legend=QVBoxLayout(); legend.addStretch(); self.level_legend=[]
        for color,text in [(PALETTE["green"],"Healthy · 0"),(PALETTE["orange"],"Needs attention · 0"),(PALETTE["red"],"Critical · 0")]:
            row=QHBoxLayout(); dot=label("●"); dot.setStyleSheet(f"color:{color};font-size:12px;"); row.addWidget(dot); value=label(text,"muted"); row.addWidget(value); row.addStretch(); legend.addLayout(row); legend.addSpacing(12); self.level_legend.append(value)
        legend.addStretch(); chartrow.addLayout(legend,3); ll.addLayout(chartrow); middle.addWidget(level_card,2)
        usage=card(); ul=QVBoxLayout(usage); ul.setContentsMargins(18,16,18,16); ul.setSpacing(8)
        uh=QHBoxLayout(); uh.addWidget(section_heading("Water usage today", "Distribution network · litres / hour")); uh.addStretch(); delta=label("↗  8.4%", "muted"); delta.setStyleSheet("color:#14835F;font-weight:700;"); uh.addWidget(delta,0,Qt.AlignmentFlag.AlignTop); ul.addLayout(uh); ul.addWidget(UsageChart()); middle.addWidget(usage,3)
        root.addLayout(middle,1)
        bottom=QHBoxLayout(); bottom.setSpacing(14)
        alert_card=card(); al=QVBoxLayout(alert_card); al.setContentsMargins(18,16,18,16); ah=QHBoxLayout(); ah.addWidget(section_heading("Latest alerts","Needs your attention")); ah.addStretch(); self.view_all_button=make_button("View all →"); ah.addWidget(self.view_all_button); al.addLayout(ah); self.alert_list=QVBoxLayout(); al.addLayout(self.alert_list); bottom.addWidget(alert_card,3)
        maintenance=card(); ml=QVBoxLayout(maintenance); ml.setContentsMargins(18,16,18,16); ml.addWidget(section_heading("Maintenance tasks","Field team activity"))
        for title,sub,status in [("Pump inspection · TNK-003","Riverside · Joseph K.","In progress"),("Valve replacement · TNK-002","Hillview · Mariama S.","Scheduled")]:
            row=QHBoxLayout(); icon=label("⚙"); icon.setStyleSheet("font-size:19px;color:#1687D9;"); row.addWidget(icon); col=QVBoxLayout(); col.addWidget(label(title)); col.addWidget(label(sub,"muted")); row.addLayout(col,1); badge=label(status); badge.setStyleSheet("color:#B7791F;background:#FFF4DE;padding:5px 8px;border-radius:8px;font-size:10px;"); row.addWidget(badge); ml.addLayout(row)
        bottom.addWidget(maintenance,2); root.addLayout(bottom,1); self.refresh()

    def refresh(self):
        tanks, alerts, communities = self.repo.tanks(), self.repo.alerts(), self.repo.communities()
        self.level_chart.set_tanks(tanks)
        counts=[sum(t.status==status for t in tanks) for status in ("Normal","Warning","Critical")]
        for target,color,count in zip(self.level_legend,("Healthy","Needs attention","Critical"),counts): target.setText(f"{color} · {count}")
        values={"communities":str(len(communities)),"tanks":str(len(tanks)),"water":f"{sum(t.level for t in tanks):,} L","alerts":str(sum(not a.resolved for a in alerts))}
        for widget,key in self._metric_cards: widget.setText(values[key])
        while self.alert_list.count():
            item=self.alert_list.takeAt(0); w=item.widget()
            if w: w.deleteLater()
        for alert in [a for a in alerts if not a.resolved][:3]:
            row=QHBoxLayout(); dot=label("●"); color=PALETTE["red"] if alert.severity=="Critical" else PALETTE["orange"] if alert.severity=="Warning" else PALETTE["blue"]; dot.setStyleSheet(f"color:{color};"); row.addWidget(dot); col=QVBoxLayout(); col.addWidget(label(alert.title)); col.addWidget(label(f"{alert.tank}  ·  {alert.time}","muted")); row.addLayout(col,1); self.alert_list.addLayout(row)


class TanksPage(QWidget):
    def __init__(self, repo: AssetRepository, changed):
        super().__init__(); self.repo,self.changed=repo,changed; root=QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(14)
        head=QHBoxLayout(); head.addWidget(section_heading("Tank management","Monitor levels, flow and connected equipment.")); head.addStretch(); self.search=QLineEdit(); self.search.setPlaceholderText("⌕  Search tanks..."); self.search.setMaximumWidth(220); self.filter=QComboBox(); self.filter.addItem("All communities"); self.filter.addItems([c.name for c in repo.communities()]); add=make_button("＋  Add tank",True); add.clicked.connect(self.add_tank); head.addWidget(self.search); head.addWidget(self.filter); head.addWidget(add); root.addLayout(head)
        summary=QHBoxLayout()
        self.summary_values=[]
        for text,detail,color in [("0 connected","All network tanks",PALETTE["blue"]),("0% average","Network fill level",PALETTE["green"]),("0 critical","Immediate follow-up",PALETTE["red"])]:
            f=card(); l=QVBoxLayout(f); l.setContentsMargins(15,12,15,12); v=label(text); v.setStyleSheet(f"font-size:17px;font-weight:700;color:{color};"); l.addWidget(v); l.addWidget(label(detail,"muted")); summary.addWidget(f); self.summary_values.append(v)
        root.addLayout(summary)
        self.table=QTableWidget(0,7); self.table.setHorizontalHeaderLabels(["TANK / COMMUNITY","LEVEL","CAPACITY","FLOW","VALVE","STATUS","ACTIONS"]); self.table.verticalHeader().setVisible(False); self.table.setShowGrid(False); self.table.setAlternatingRowColors(True); self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows); self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); self.table.setWordWrap(False); self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter); self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch); self.table.horizontalHeader().setSectionResizeMode(6,QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self.table,1); self.search.textChanged.connect(self.refresh); self.filter.currentTextChanged.connect(self.refresh); self.refresh()

    def refresh(self):
        query=self.search.text().lower(); community=self.filter.currentText(); tanks=[t for t in self.repo.tanks() if (not query or query in t.name.lower() or query in t.community.lower()) and (community=="All communities" or t.community==community)]
        all_tanks=self.repo.tanks(); average=round(sum(t.percentage for t in all_tanks)/len(all_tanks)) if all_tanks else 0
        for widget,value in zip(self.summary_values,(f"{len(all_tanks):02d} connected",f"{average}% average",f"{sum(t.status=='Critical' for t in all_tanks):02d} critical")): widget.setText(value)
        self.table.setRowCount(len(tanks))
        for r,t in enumerate(tanks):
            c=QWidget(); cl=QVBoxLayout(c); cl.setContentsMargins(8,5,8,5); cl.addWidget(label(t.name)); cl.addWidget(label(f"{t.community} · Updated {t.updated}","muted")); self.table.setCellWidget(r,0,c)
            bar=QWidget(); bl=QVBoxLayout(bar); bl.setContentsMargins(8,10,8,10); pct=label(f"{t.percentage}%"); pct.setStyleSheet(f"color:{PALETTE['red'] if t.percentage<30 else PALETTE['orange'] if t.percentage<50 else PALETTE['green']};font-weight:700;"); bl.addWidget(pct); self.table.setCellWidget(r,1,bar)
            self.table.setItem(r,2,QTableWidgetItem(f"{t.capacity:,} L")); self.table.setItem(r,3,QTableWidgetItem(f"{t.flow:g} L/min")); self.table.setItem(r,4,QTableWidgetItem("●  "+t.valve))
            badge=QLabel("  "+t.status+"  "); color=PALETTE["green"] if t.status=="Normal" else PALETTE["orange"] if t.status=="Warning" else PALETTE["red"]; badge.setStyleSheet(f"color:{color};background:#18{color[1:]};border-radius:8px;padding:5px;font-weight:600;"); badge.setAlignment(Qt.AlignmentFlag.AlignCenter); self.table.setCellWidget(r,5,badge)
            actions=QWidget(); ar=QHBoxLayout(actions); ar.setContentsMargins(2,4,2,4); edit=QPushButton("Edit"); delete=QPushButton("Delete"); edit.clicked.connect(lambda checked=False,x=t:self.edit_tank(x)); delete.clicked.connect(lambda checked=False,x=t:self.delete_tank(x)); ar.addWidget(edit); ar.addWidget(delete); self.table.setCellWidget(r,6,actions); self.table.setRowHeight(r,62)

    def add_tank(self):
        dlg=TankDialog(self.repo.communities())
        if dlg.exec():
            try: self.repo.save_tank(dlg.value()); self.refresh(); self.changed()
            except Exception as exc: QMessageBox.warning(self,"Could not save tank",str(exc))
    def edit_tank(self,tank):
        dlg=TankDialog(self.repo.communities(),tank)
        if dlg.exec():
            try: self.repo.save_tank(dlg.value()); self.refresh(); self.changed()
            except Exception as exc: QMessageBox.warning(self,"Could not save tank",str(exc))
    def delete_tank(self,tank):
        if QMessageBox.question(self,"Delete tank",f"Delete {tank.name}? This action cannot be undone.")==QMessageBox.StandardButton.Yes:
            self.repo.delete_tank(tank.asset_id); self.refresh(); self.changed()


class CommunityDialog(QDialog):
    def __init__(self, community: Optional[Community] = None):
        super().__init__(); self.community_id = community.community_id if community else 0
        self.setWindowTitle("Community details"); self.setMinimumWidth(440)
        root=QVBoxLayout(self); root.setContentsMargins(24,22,24,18); root.setSpacing(16)
        root.addWidget(label("Community information","sectionTitle")); form=QFormLayout(); form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow); form.setHorizontalSpacing(18); form.setVerticalSpacing(12)
        self.name=QLineEdit(community.name if community else ""); self.name.setPlaceholderText("e.g. Brookside")
        self.location=QLineEdit(community.location if community else ""); self.location.setPlaceholderText("District or service area")
        self.households=QLineEdit(str(community.households) if community else "0"); self.households.setPlaceholderText("Number of households")
        form.addRow("Community name",self.name); form.addRow("Location",self.location); form.addRow("Households",self.households); root.addLayout(form)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel|QDialogButtonBox.StandardButton.Save); buttons.accepted.connect(self._validate); buttons.rejected.connect(self.reject); root.addWidget(buttons)
    def _validate(self):
        try:
            if not self.name.text().strip() or not self.location.text().strip(): raise ValueError("Enter a community name and location.")
            if int(self.households.text()) < 0: raise ValueError("Households cannot be negative.")
        except ValueError as exc: QMessageBox.warning(self,"Check community details",str(exc)); return
        self.accept()
    def value(self): return Community(self.community_id,self.name.text().strip(),self.location.text().strip(),0,int(self.households.text()))


class CommunityPage(QWidget):
    def __init__(self, repo: AssetRepository, changed):
        super().__init__(); self.repo,self.changed=repo,changed
        root=QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(16)
        top=QHBoxLayout(); top.setSpacing(14); top.addWidget(section_heading("Communities","Manage service areas and connected households.")); top.addStretch()
        self.search=QLineEdit(); self.search.setPlaceholderText("Search communities…"); self.search.setMaximumWidth(260); top.addWidget(self.search)
        add=make_button("＋  Add community",True); add.clicked.connect(self.add_community); top.addWidget(add); root.addLayout(top)
        frame=card(); layout=QVBoxLayout(frame); layout.setContentsMargins(8,8,8,8)
        self.table=QTableWidget(0,5); self.table.setHorizontalHeaderLabels(["COMMUNITY","LOCATION","TANKS","HOUSEHOLDS","ACTIONS"]); self.table.verticalHeader().setVisible(False); self.table.setShowGrid(False); self.table.setAlternatingRowColors(True); self.table.setWordWrap(False); self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter); self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch); self.table.horizontalHeader().setSectionResizeMode(4,QHeaderView.ResizeMode.ResizeToContents); layout.addWidget(self.table); root.addWidget(frame,1)
        self.search.textChanged.connect(self._filter); self.refresh()
    def refresh(self):
        communities=self.repo.communities(); self.table.setRowCount(len(communities))
        for row,item in enumerate(communities):
            values=[item.name,item.location,str(item.tanks),f"{item.households:,}"]
            for col,value in enumerate(values): self.table.setItem(row,col,QTableWidgetItem(value))
            cell=QWidget(); cell_layout=QHBoxLayout(cell); cell_layout.setContentsMargins(4,4,4,4); cell_layout.setSpacing(6)
            edit=QPushButton("Edit"); delete=QPushButton("Delete"); edit.clicked.connect(lambda checked=False,c=item:self.edit_community(c)); delete.clicked.connect(lambda checked=False,c=item:self.delete_community(c)); cell_layout.addWidget(edit); cell_layout.addWidget(delete); self.table.setCellWidget(row,4,cell); self.table.setRowHeight(row,56)
        self._filter(self.search.text())
    def _filter(self,query):
        query=query.casefold()
        for row in range(self.table.rowCount()):
            visible=any(query in (self.table.item(row,col).text().casefold() if self.table.item(row,col) else "") for col in range(4))
            self.table.setRowHidden(row,bool(query) and not visible)
    def add_community(self):
        dialog=CommunityDialog()
        if dialog.exec()==QDialog.DialogCode.Accepted: self._save(dialog.value())
    def edit_community(self,community):
        dialog=CommunityDialog(community)
        if dialog.exec()==QDialog.DialogCode.Accepted: self._save(dialog.value())
    def _save(self,community):
        try: self.repo.save_community(community); self.refresh(); self.changed()
        except Exception as exc: QMessageBox.critical(self,"Save failed",str(exc))
    def delete_community(self,community):
        if QMessageBox.question(self,"Delete community",f"Delete {community.name}? Tanks in this community will become unassigned.")==QMessageBox.StandardButton.Yes:
            try: self.repo.delete_community(community.community_id); self.refresh(); self.changed()
            except Exception as exc: QMessageBox.critical(self,"Delete failed",str(exc))


class GenericRecordDialog(QDialog):
    """Consistent validated form used by database-backed operations lists."""
    def __init__(self, title: str, headers: tuple[str, ...], values: Optional[list[str]] = None):
        super().__init__(); self.setWindowTitle(title); self.setMinimumWidth(440)
        self.fields: list[QLineEdit] = []
        root=QVBoxLayout(self); root.setContentsMargins(24,22,24,18); root.setSpacing(16)
        root.addWidget(label(title,"sectionTitle")); form=QFormLayout(); form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow); form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter); form.setHorizontalSpacing(18); form.setVerticalSpacing(12)
        for index, header in enumerate(headers):
            edit=QLineEdit(values[index] if values and index<len(values) else "")
            edit.setMinimumWidth(250); edit.setPlaceholderText(f"Enter {header.lower()}")
            form.addRow(header,edit); self.fields.append(edit)
        root.addLayout(form); buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel|QDialogButtonBox.StandardButton.Save)
        buttons.accepted.connect(self._validate); buttons.rejected.connect(self.reject); root.addWidget(buttons)
    def _validate(self):
        if not self.fields or any(not field.text().strip() for field in self.fields):
            QMessageBox.warning(self,"Required fields", "Complete all fields before saving this record."); return
        self.accept()
    def value(self) -> list[str]: return [field.text().strip() for field in self.fields]


class SettingsPage(QWidget):
    def __init__(self, theme_changed):
        super().__init__(); root=QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(16)
        root.addWidget(section_heading("Profile & settings","Manage your operator account and application preferences."))
        account=card(); al=QVBoxLayout(account); al.setContentsMargins(20,18,20,18); al.addWidget(label("Operator profile","sectionTitle")); al.addWidget(label("Amina Mansaray · System operator")); al.addWidget(label("amina@swims.gov.sl","muted")); root.addWidget(account)
        prefs=card(); pl=QVBoxLayout(prefs); pl.setContentsMargins(20,18,20,18); pl.addWidget(label("Preferences","sectionTitle")); self.dark=QCheckBox("Use dark appearance"); self.dark.toggled.connect(theme_changed); pl.addWidget(self.dark); notifications=QCheckBox("Receive critical alert notifications"); notifications.setChecked(True); pl.addWidget(notifications); root.addWidget(prefs); root.addStretch()


class ReportsPage(QWidget):
    def __init__(self, repo: AssetRepository):
        super().__init__(); self.repo=repo; root=QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(16)
        root.addWidget(section_heading("Reports & exports","Download current operational data as spreadsheet-ready CSV files."))
        self.report_rows=[
            ("Water usage report","Transactions and recorded volumes","usage"),
            ("Tank status report","Capacity, level, flow and valve status","tanks"),
            ("Alert report","Open and resolved network alerts","alerts"),
            ("Maintenance report","Scheduled and completed field work","maintenance"),
        ]
        for title,description,category in self.report_rows:
            frame=card(); row=QHBoxLayout(frame); row.setContentsMargins(18,14,18,14); details=QVBoxLayout(); details.addWidget(label(title,"sectionTitle")); details.addWidget(label(description,"muted")); row.addLayout(details,1); button=make_button("Export CSV"); button.clicked.connect(lambda checked=False,c=category:self.export(c)); row.addWidget(button); root.addWidget(frame)
        root.addStretch()
    def export(self,category):
        import csv
        if category=="usage": headers=RECORD_SCHEMAS["transactions"]; rows=[fields for _,fields in self.repo.records("transactions")]; name="water_usage"
        elif category=="maintenance": headers=RECORD_SCHEMAS["maintenance"]; rows=[fields for _,fields in self.repo.records("maintenance")]; name="maintenance"
        elif category=="tanks":
            headers=("Tank code","Community","Capacity (L)","Current level (L)","Percentage","Flow (L/min)","Valve","Status")
            rows=[[tank.name,tank.community,tank.capacity,tank.level,tank.percentage,tank.flow,tank.valve,tank.status] for tank in self.repo.tanks()]; name="tank_status"
        else:
            headers=("Alert","Tank","Severity","Time","Details","Resolved")
            rows=[[alert.title,alert.tank,alert.severity,alert.time,alert.detail,alert.resolved] for alert in self.repo.alerts()]; name="alerts"
        path,_=QFileDialog.getSaveFileName(self,"Export report",f"swims_{name}.csv","CSV files (*.csv)")
        if not path: return
        try:
            with open(path,"w",newline="",encoding="utf-8-sig") as output:
                writer=csv.writer(output); writer.writerow(headers); writer.writerows(rows)
            QMessageBox.information(self,"Export complete",f"Report saved to:\n{path}")
        except OSError as exc: QMessageBox.critical(self,"Export failed",str(exc))


class GenericPage(QWidget):
    """Searchable CRUD table backed by the selected repository category."""
    def __init__(self, repo: AssetRepository, category: str, title: str, description: str,
                 headers: tuple[str, ...]):
        super().__init__(); self.repo,self.category,self.title,self.headers=repo,category,title,headers
        root=QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(16)
        top=QHBoxLayout(); top.setSpacing(14); top.addWidget(section_heading(title,description)); top.addStretch()
        self.search=QLineEdit(); self.search.setPlaceholderText("Search records…"); self.search.setMaximumWidth(260)
        add=make_button("＋  Add record",True); add.clicked.connect(self.add_record)
        export=make_button("Export CSV"); export.clicked.connect(self.export_csv)
        top.addWidget(self.search); top.addWidget(export); top.addWidget(add); root.addLayout(top)
        table_card=card(); card_layout=QVBoxLayout(table_card); card_layout.setContentsMargins(8,8,8,8)
        self.table=QTableWidget(0,len(headers)+1); self.table.setHorizontalHeaderLabels([*headers,"ACTIONS"])
        self.table.verticalHeader().setVisible(False); self.table.setShowGrid(False); self.table.setAlternatingRowColors(True); self.table.setWordWrap(False); self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows); self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(len(headers),QHeaderView.ResizeMode.ResizeToContents)
        card_layout.addWidget(self.table); root.addWidget(table_card,1)
        self.search.textChanged.connect(self._filter); self.refresh()
    def refresh(self):
        rows=self.repo.records(self.category); self.table.setRowCount(len(rows))
        for row,(record_id,fields) in enumerate(rows):
            for column,value in enumerate(fields):
                item=QTableWidgetItem(str(value)); item.setData(Qt.ItemDataRole.UserRole,record_id); self.table.setItem(row,column,item)
            actions=QWidget(); actions.setObjectName("tableActions"); actions_layout=QHBoxLayout(actions); actions_layout.setContentsMargins(4,4,4,4); actions_layout.setSpacing(6)
            edit=QPushButton("Edit"); delete=QPushButton("Delete"); edit.clicked.connect(lambda checked=False,i=record_id,f=list(fields):self.edit_record(i,f)); delete.clicked.connect(lambda checked=False,i=record_id:self.delete_record(i)); actions_layout.addWidget(edit); actions_layout.addWidget(delete)
            self.table.setCellWidget(row,len(self.headers),actions); self.table.setRowHeight(row,56)
        self._filter(self.search.text())
    def _filter(self,query):
        query=query.casefold()
        for row in range(self.table.rowCount()):
            match=any(query in (self.table.item(row,col).text().casefold() if self.table.item(row,col) else "") for col in range(len(self.headers)))
            self.table.setRowHidden(row,bool(query) and not match)
    def add_record(self):
        dialog=GenericRecordDialog(f"Add {self.title.rstrip('s').lower()}",self.headers)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self._save(0,dialog.value())
    def edit_record(self,record_id,values):
        dialog=GenericRecordDialog(f"Edit {self.title.rstrip('s').lower()}",self.headers,values)
        if dialog.exec()==QDialog.DialogCode.Accepted: self._save(record_id,dialog.value())
    def _save(self,record_id,values):
        try: self.repo.save_record(self.category,record_id,values); self.refresh()
        except Exception as exc: QMessageBox.critical(self,"Save failed",str(exc))
    def delete_record(self,record_id):
        if QMessageBox.question(self,"Delete record","Delete this record permanently?")==QMessageBox.StandardButton.Yes:
            try: self.repo.delete_record(self.category,record_id); self.refresh()
            except Exception as exc: QMessageBox.critical(self,"Delete failed",str(exc))
    def export_csv(self):
        import csv
        path,_=QFileDialog.getSaveFileName(self,"Export records",f"swims_{self.category}.csv","CSV files (*.csv)")
        if not path: return
        try:
            with open(path,"w",newline="",encoding="utf-8-sig") as output:
                writer=csv.writer(output); writer.writerow(self.headers)
                for _,fields in self.repo.records(self.category): writer.writerow(fields)
            QMessageBox.information(self,"Export complete",f"Saved {self.title.lower()} to:\n{path}")
        except OSError as exc: QMessageBox.critical(self,"Export failed",str(exc))


class AlertsPage(QWidget):
    def __init__(self, repo: AssetRepository):
        super().__init__(); self.repo=repo; root=QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(16); top=QHBoxLayout(); top.addWidget(section_heading("Alerts & incidents","Review network events and close resolved issues.")); top.addStretch(); root.addLayout(top)
        self.list=QVBoxLayout(); self.list.setSpacing(10); root.addLayout(self.list); root.addStretch(); self.refresh()
    def refresh(self):
        while self.list.count():
            item=self.list.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        for a in self.repo.alerts():
            f=card(); row=QHBoxLayout(f); row.setContentsMargins(16,13,16,13); dot=label("!"); col=PALETTE["red"] if a.severity=="Critical" else PALETTE["orange"] if a.severity=="Warning" else PALETTE["blue"]; dot.setStyleSheet(f"color:{col};background:#18{col[1:]};border-radius:16px;padding:9px;font-size:16px;font-weight:700;"); row.addWidget(dot)
            txt=QVBoxLayout(); txt.addWidget(label(a.title)); txt.addWidget(label(f"{a.tank}  ·  {a.time}","muted")); txt.addWidget(label(a.detail,"muted")); row.addLayout(txt,1); badge=label("Resolved" if a.resolved else a.severity); badge.setStyleSheet(f"color:{col};font-weight:700;"); row.addWidget(badge)
            if not a.resolved:
                button=make_button("Mark resolved"); button.clicked.connect(lambda checked=False,x=a:self.resolve(x)); row.addWidget(button)
            self.list.addWidget(f)
    def resolve(self,alert):
        try: self.repo.resolve_alert(alert.alert_id); self.refresh()
        except Exception as exc: QMessageBox.critical(self,"Could not resolve alert",str(exc))


class SwimsWindow(QMainWindow):
    def __init__(self, repo: AssetRepository, demo: bool):
        super().__init__(); self.repo=repo; self.demo=demo; self.setWindowTitle("SWIMS · Smart Water Infrastructure Management System")
        available=QApplication.primaryScreen().availableGeometry(); width=max(900,min(1440,available.width()-32)); height=max(620,min(900,available.height()-48))
        self.setMinimumSize(min(980,width),min(660,height)); self.resize(width,height)
        shell=QWidget(); self.setCentralWidget(shell); outer=QHBoxLayout(shell); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        sidebar=QFrame(); sidebar.setObjectName("sidebar"); sidebar.setFixedWidth(226); sl=QVBoxLayout(sidebar); sl.setContentsMargins(15,22,15,16); sl.setSpacing(5)
        brand=QHBoxLayout(); mark=QLabel("≈"); mark.setAlignment(Qt.AlignmentFlag.AlignCenter); mark.setFixedSize(38,38); mark.setStyleSheet("background:#1687D9;color:white;border-radius:12px;font-size:27px;font-weight:700;"); brand.addWidget(mark); names=QVBoxLayout(); n=QLabel("SWIMS"); n.setStyleSheet("color:white;font-size:17px;font-weight:800;letter-spacing:1px;"); names.addWidget(n); sub=QLabel("WATER OPERATIONS"); sub.setStyleSheet("color:#91A9BB;font-size:8px;letter-spacing:1px;"); names.addWidget(sub); brand.addLayout(names); brand.addStretch(); sl.addLayout(brand); sl.addSpacing(26)
        cap=QLabel("WORKSPACE"); cap.setStyleSheet("color:#7891A5;font-size:9px;font-weight:700;letter-spacing:1.2px;padding-left:12px;"); sl.addWidget(cap); sl.addSpacing(7)
        self.stack=QStackedWidget(); self.nav_buttons=[]; self.pages=[]
        names=[("⌂","Dashboard"),("▤","Communities"),("◉","Tank management"),("◌","Sensors"),("!","Alerts"),("↕","Transactions"),("⚙","Equipment"),("▣","Maintenance"),("♙","Technicians"),("▥","Reports"),("●","Profile & settings")]
        for icon,title in names:
            b=QPushButton(f"{icon}    {title}"); b.setObjectName("nav"); b.setProperty("selected",title=="Dashboard"); b.clicked.connect(lambda checked=False,x=title:self.navigate(x)); sl.addWidget(b); self.nav_buttons.append((title,b))
        sl.addStretch(); profile=QFrame(); profile.setStyleSheet("background:#1B3A53;border-radius:12px;"); pl=QHBoxLayout(profile); pl.setContentsMargins(10,10,10,10); avatar=QLabel("AM"); avatar.setAlignment(Qt.AlignmentFlag.AlignCenter); avatar.setFixedSize(34,34); avatar.setStyleSheet("background:#2E607D;color:white;border-radius:17px;font-weight:700;"); pl.addWidget(avatar); ptxt=QVBoxLayout(); pn=QLabel("Amina Mansaray"); pn.setStyleSheet("color:white;font-size:11px;font-weight:600;"); pr=QLabel("System operator"); pr.setStyleSheet("color:#91A9BB;font-size:10px;"); ptxt.addWidget(pn); ptxt.addWidget(pr); pl.addLayout(ptxt); sl.addWidget(profile); outer.addWidget(sidebar)
        body=QWidget(); bl=QVBoxLayout(body); bl.setContentsMargins(27,20,27,20); bl.setSpacing(18)
        top=QHBoxLayout(); breadcrumb=QLabel("Operations  /  <b>Dashboard</b>"); breadcrumb.setStyleSheet("color:#8295A6;"); top.addWidget(breadcrumb); top.addStretch(); self.conn=QLabel("●  DEMO DATA" if demo else "●  POSTGRESQL CONNECTED"); self.conn.setStyleSheet("color:#14835F;background:#E5F6EF;border-radius:9px;padding:7px 10px;font-size:10px;font-weight:700;"); top.addWidget(self.conn); self.theme_button=QPushButton("◐  Dark mode"); self.theme_button.setCheckable(True); self.theme_button.toggled.connect(self.toggle_theme); top.addWidget(self.theme_button); bell=QPushButton("♧  3"); bell.clicked.connect(lambda:self.navigate("Alerts")); top.addWidget(bell); bl.addLayout(top)
        self.page_stack=QStackedWidget(); bl.addWidget(self.page_stack,1); outer.addWidget(body,1); self.breadcrumb=breadcrumb
        self.dashboard=DashboardPage(repo); self.dashboard.view_all_button.clicked.connect(lambda:self.navigate("Alerts")); self.tanks=TanksPage(repo,self.refresh_dashboard); self.alerts=AlertsPage(repo)
        profile=SettingsPage(self.toggle_theme); self.settings=profile
        self.page_map={"Dashboard":self.dashboard,
            "Communities":CommunityPage(repo,self.community_changed),
            "Tank management":self.tanks,
            "Sensors":GenericPage(repo,"sensors","Sensor monitoring","Live health and readings from connected field devices.",RECORD_SCHEMAS["sensors"]),
            "Alerts":self.alerts,
            "Transactions":GenericPage(repo,"transactions","Water transactions","Inflow and consumption records from across the network.",RECORD_SCHEMAS["transactions"]),
            "Equipment":GenericPage(repo,"equipment","Equipment","Pumps, valves, flow meters and control units.",RECORD_SCHEMAS["equipment"]),
            "Maintenance":GenericPage(repo,"maintenance","Maintenance","Track field work and upcoming service activities.",RECORD_SCHEMAS["maintenance"]),
            "Technicians":GenericPage(repo,"technicians","Technicians","Field team directory and assigned responsibilities.",RECORD_SCHEMAS["technicians"]),
            "Reports":ReportsPage(repo),
            "Profile & settings":profile}
        for _, title in names: self.page_stack.addWidget(self.page_map[title])
        footer=QHBoxLayout(); footer.addWidget(label("●  All systems operational  ·  Last sync 09:42:18","muted")); footer.addStretch(); footer.addWidget(label("SWIMS v1.0.0  ·  Water services dashboard","muted")); bl.addLayout(footer)
        self.navigate("Dashboard")

    def navigate(self,title):
        index=list(self.page_map).index(title); self.page_stack.setCurrentIndex(index); self.breadcrumb.setText(f"Operations  /  <b>{title}</b>")
        for name,button in self.nav_buttons: button.setProperty("selected",name==title); button.style().unpolish(button); button.style().polish(button)
        if title=="Dashboard": self.dashboard.refresh()
        if title=="Alerts": self.alerts.refresh()
    def refresh_dashboard(self): self.dashboard.refresh()
    def community_changed(self):
        self.dashboard.refresh()
        self.tanks.filter.blockSignals(True)
        current=self.tanks.filter.currentText()
        available=[community.name for community in self.repo.communities()]
        self.tanks.filter.clear(); self.tanks.filter.addItem("All communities")
        self.tanks.filter.addItems(available)
        self.tanks.filter.setCurrentText(current if current in ["All communities"]+available else "All communities")
        self.tanks.filter.blockSignals(False); self.tanks.refresh()
    def toggle_theme(self, dark: bool):
        QApplication.instance().setStyleSheet(DARK_STYLE if dark else APP_STYLE)
        self.theme_button.setText("☼  Light mode" if dark else "◐  Dark mode")
        if hasattr(self,"settings") and self.settings.dark.isChecked()!=dark:
            self.settings.dark.blockSignals(True); self.settings.dark.setChecked(dark); self.settings.dark.blockSignals(False)


def load_local_environment(path: Path = Path(".env")) -> None:
    """Read simple KEY=VALUE entries; process-level variables take precedence."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line=raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line=line[7:].lstrip()
        if "=" not in line:
            continue
        key,value=line.split("=",1); key=key.strip(); value=value.strip()
        if len(value)>=2 and value[0]==value[-1] and value[0] in ("'",'"'):
            value=value[1:-1]
        if key and key not in os.environ:
            os.environ[key]=value


def main() -> int:
    app=QApplication(sys.argv); app.setApplicationName("SWIMS"); app.setStyle("Fusion"); app.setStyleSheet(APP_STYLE)
    load_local_environment()
    dsn=os.environ.get("SWIMS_DATABASE_URL","").strip()
    db_keys=("DB_HOST","DB_PORT","DB_NAME","DB_USER")
    if dsn:
        database_config: str | dict[str, object] = dsn
    elif any(os.environ.get(key,"").strip() for key in (*db_keys,"DB_PASSWORD")):
        missing=[key for key in db_keys if not os.environ.get(key,"").strip()]
        if missing:
            QMessageBox.critical(None,"Incomplete database settings","Add these values to .env: " + ", ".join(missing)); return 1
        try:
            database_config = {"host":os.environ["DB_HOST"].strip(),"port":int(os.environ["DB_PORT"].strip()),
                               "dbname":os.environ["DB_NAME"].strip(),"user":os.environ["DB_USER"].strip(),
                               "password":os.environ.get("DB_PASSWORD","")}
        except ValueError:
            QMessageBox.critical(None,"Invalid database settings","DB_PORT in .env must be a number."); return 1
    else:
        database_config = ""
    demo=not bool(database_config)
    try: repo=PostgresRepository(database_config) if not demo else DemoRepository()
    except Exception as exc:
        QMessageBox.critical(None,"Database connection failed",f"SWIMS could not connect to PostgreSQL.\n\n{exc}\n\nSet SWIMS_DATABASE_URL and restart."); return 1
    login=LoginDialog()
    if login.exec()!=QDialog.DialogCode.Accepted: return 0
    window=SwimsWindow(repo,demo); window.show(); return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
