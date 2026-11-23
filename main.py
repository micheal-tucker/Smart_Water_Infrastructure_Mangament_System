"""SWIMS: Smart Water Infrastructure Management System.

Python + PyQt6 desktop application for community water operations.
Set SWIMS_DATABASE_URL to connect to PostgreSQL. Without it, the app opens
with clearly labelled sample data so the interface can be explored offline.
"""

from __future__ import annotations

import os
import sys
import math
from pathlib import Path
from xml.sax.saxutils import escape
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QFileDialog, QSizePolicy, QScrollArea,
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

    def __init__(self, asset_id: int, code: str, community: str, capacity: float,
                 level: float, flow: float, valve: str, status: str,
                 updated: str = "Just now", installed: str = ""):
        super().__init__(asset_id, code, community, status)
        self._capacity, self._level = capacity, level
        self.flow, self.valve, self.updated, self.installed = flow, valve, updated, installed

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

    @property
    def health(self) -> str:
        state=self.status.upper()
        if state in ("CRITICAL","FAULT","MAINTENANCE","OUT_OF_SERVICE","INACTIVE"): return "Critical"
        if state in ("WARNING","LOW_WATER"): return "Warning"
        if self.percentage < 30: return "Critical"
        if self.percentage < 50: return "Warning"
        return "Normal"

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
    "sensors": ("Sensor code", "Sensor type", "Tank code", "Latest reading (value + unit)", "Status"),
    "transactions": ("Tank code", "Transaction type", "Volume (L)", "Transaction date/time", "Level after (L)"),
    "equipment": ("Equipment name", "Equipment type", "Tank code", "Status", "Installation date"),
    "maintenance": ("Maintenance type", "Equipment name", "Technician name", "Status", "Date", "Notes"),
    "technicians": ("First name", "Last name", "Phone number", "Email", "Specialization"),
    "valves": ("Valve code", "Tank code", "Valve status", "Installation date"),
}

SEED_RECORDS = {
    "sensors": [
        ["SEN-UL-001", "Ultrasonic", "TNK-001", "2.04 m", "ACTIVE"],
        ["SEN-FL-002", "Flow", "TNK-002", "9.2 L/min", "ACTIVE"],
        ["SEN-UL-003", "Ultrasonic", "TNK-003", "0.83 m", "WARNING"],
    ],
    "transactions": [
        ["TNK-001", "INFLOW", "2400", "2026-11-22 09:42", "20400"],
        ["TNK-002", "USAGE", "840", "2026-11-22 09:30", "6840"],
    ],
    "equipment": [
        ["Booster pump", "Pump", "TNK-001", "OPERATIONAL", "2025-06-12"],
        ["Control valve", "Valve", "TNK-003", "MAINTENANCE", "2025-03-08"],
    ],
    "maintenance": [
        ["Pump inspection", "Booster pump", "Joseph Kamara", "In progress", "2026-11-22", "Routine check"],
        ["Valve replacement", "Control valve", "Mariama Sesay", "Scheduled", "2026-11-24", "Replace worn valve"],
    ],
    "technicians": [
        ["Joseph", "Kamara", "+232 76 555 018", "j.kamara@swims.gov.sl", "Pumps & motors"],
        ["Mariama", "Sesay", "+232 77 210 044", "m.sesay@swims.gov.sl", "Valves & controls"],
    ],
    "valves": [["VL-001","TNK-001","OPEN","2025-06-12"]],
}

REQUIRED_RECORD_FIELDS = {
    "sensors": (0,1,2,3,4), "transactions": (0,1,2,3),
    "equipment": (0,1,2,3), "maintenance": (0,1,2,3,4),
    "technicians": (0,1), "valves": (0,1,2),
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
        if deleted and any(tank.community==deleted.name for tank in self._tanks):
            raise ValueError("This community still has tanks. Reassign or remove its tanks first.")
        self._communities = [item for item in self._communities if item.community_id != community_id]

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
        self._validate_schema()

    def _validate_schema(self) -> None:
        with self._db.cursor() as cur:
            cur.execute("""SELECT table_name,column_name FROM information_schema.columns
                WHERE table_schema='public'""")
            available={}
            for table,column in cur.fetchall(): available.setdefault(table,set()).add(column)
            required={
                "communities":{"community_id","community_name","household_count","location"},
                "water_tanks":{"tank_id","community_id","tank_code","capacity_litres","current_level","installation_date","status"},
                "sensors":{"sensor_id","tank_id","sensor_code","sensor_type","status"},
                "sensor_readings":{"reading_id","sensor_id","reading_value","reading_unit","reading_time"},
                "valves":{"valve_id","tank_id","valve_code","valve_status","installation_date"},
                "water_transactions":{"transaction_id","tank_id","transaction_type","litres","transaction_date","level_after"},
                "equipment":{"equipment_id","tank_id","equipment_name","equipment_type","installation_date","status"},
                "maintenance":{"maintenance_id","technician_id","equipment_id","maintenance_type","maintenance_date","notes"},
                "technicians":{"technician_id","first_name","last_name","phone_number","email","specialisation"},
                "alerts":{"alert_id","tank_id","alert_type","alert_message","alert_date","resolved"},
            }
            missing=[f"{table}.{column}" for table,columns in required.items() for column in columns if column not in available.get(table,set())]
            if missing:
                raise RuntimeError("The configured database does not match the SWIMS schema. Missing: " + ", ".join(missing))
            # The brief tracks task status; the restored maintenance table did not include it.
            cur.execute("ALTER TABLE maintenance ADD COLUMN IF NOT EXISTS status VARCHAR(30) NOT NULL DEFAULT 'Scheduled'")

    def tanks(self) -> list[WaterTank]:
        with self._db.cursor() as cur:
            cur.execute("""SELECT w.tank_id,w.tank_code,c.community_name,w.capacity_litres,w.current_level,
                COALESCE((SELECT r.reading_value FROM sensor_readings r JOIN sensors s USING(sensor_id)
                    WHERE s.tank_id=w.tank_id AND LOWER(s.sensor_type)='flow' ORDER BY r.reading_time DESC,r.reading_id DESC LIMIT 1),0),
                COALESCE((SELECT v.valve_status FROM valves v WHERE v.tank_id=w.tank_id LIMIT 1),'UNKNOWN'),
                w.status,COALESCE((SELECT TO_CHAR(MAX(r.reading_time),'HH24:MI') FROM sensor_readings r
                    JOIN sensors s USING(sensor_id) WHERE s.tank_id=w.tank_id),'—'),w.installation_date
                FROM water_tanks w JOIN communities c USING(community_id) ORDER BY w.tank_code""")
            return [WaterTank(i,code,community,float(capacity),float(level),float(flow),valve,status,updated,
                              installed.isoformat() if installed else "")
                    for i,code,community,capacity,level,flow,valve,status,updated,installed in cur.fetchall()]

    def communities(self) -> list[Community]:
        with self._db.cursor() as cur:
            cur.execute("""SELECT c.community_id,c.community_name,c.location,COUNT(t.tank_id),c.household_count
                FROM communities c LEFT JOIN water_tanks t USING(community_id)
                GROUP BY c.community_id ORDER BY c.community_name""")
            return [Community(*row) for row in cur.fetchall()]

    def alerts(self) -> list[Alert]:
        with self._db.cursor() as cur:
            cur.execute("""SELECT a.alert_id,a.alert_type,w.tank_code,a.alert_date,a.alert_message,a.resolved
                FROM alerts a JOIN water_tanks w USING(tank_id) ORDER BY a.alert_date DESC""")
            result=[]
            for alert_id,kind,tank,stamp,detail,resolved in cur.fetchall():
                normalized=kind.replace("_"," ").title(); upper=kind.upper()
                severity="Critical" if any(word in upper for word in ("FAIL","MAINTENANCE","OVERFLOW")) else "Warning" if any(word in upper for word in ("LOW","ANOMALY","USAGE")) else "Info"
                result.append(Alert(alert_id,normalized,tank,severity,stamp.strftime('%Y-%m-%d %H:%M'),detail,resolved))
            return result

    def save_tank(self, tank: WaterTank) -> WaterTank:
        with self._db.cursor() as cur:
            cur.execute("SELECT community_id FROM communities WHERE community_name=%s", (tank.community,))
            row = cur.fetchone()
            if not row: raise ValueError(f"Community '{tank.community}' does not exist.")
            community_id = row[0]
            if tank.asset_id:
                cur.execute("""UPDATE water_tanks SET tank_code=%s,community_id=%s,capacity_litres=%s,
                    current_level=%s,status=%s,installation_date=%s WHERE tank_id=%s""",
                    (tank.name,community_id,tank.capacity,tank.level,tank.status,date.fromisoformat(tank.installed) if tank.installed else None,tank.asset_id))
                if cur.rowcount:
                    return tank
            cur.execute("""INSERT INTO water_tanks(tank_code,community_id,capacity_litres,current_level,status,installation_date)
                VALUES(%s,%s,%s,%s,%s,%s) RETURNING tank_id""",
                (tank.name,community_id,tank.capacity,tank.level,tank.status,date.fromisoformat(tank.installed) if tank.installed else None))
            tank._asset_id = cur.fetchone()[0]
        return tank

    def delete_tank(self, tank_id: int) -> None:
        owns_transaction=self._db.autocommit
        if owns_transaction: self._db.autocommit=False
        try:
            with self._db.cursor() as cur:
                cur.execute("DELETE FROM maintenance WHERE equipment_id IN (SELECT equipment_id FROM equipment WHERE tank_id=%s)",(tank_id,))
                cur.execute("DELETE FROM equipment WHERE tank_id=%s",(tank_id,))
                cur.execute("DELETE FROM sensor_readings WHERE sensor_id IN (SELECT sensor_id FROM sensors WHERE tank_id=%s)",(tank_id,))
                cur.execute("DELETE FROM sensors WHERE tank_id=%s",(tank_id,))
                cur.execute("DELETE FROM valves WHERE tank_id=%s",(tank_id,))
                cur.execute("DELETE FROM water_transactions WHERE tank_id=%s",(tank_id,))
                cur.execute("DELETE FROM alerts WHERE tank_id=%s",(tank_id,))
                cur.execute("DELETE FROM water_tanks WHERE tank_id=%s",(tank_id,))
            if owns_transaction: self._db.commit()
        except Exception:
            if owns_transaction: self._db.rollback()
            raise
        finally:
            if owns_transaction: self._db.autocommit=True

    def save_community(self, community: Community) -> Community:
        with self._db.cursor() as cur:
            if community.community_id:
                cur.execute("UPDATE communities SET community_name=%s,location=%s,household_count=%s WHERE community_id=%s",
                            (community.name,community.location,community.households,community.community_id))
                if cur.rowcount:
                    return community
            cur.execute("INSERT INTO communities(community_name,location,household_count) VALUES(%s,%s,%s) RETURNING community_id",
                        (community.name,community.location,community.households))
            community.community_id = cur.fetchone()[0]
        return community

    def delete_community(self, community_id: int) -> None:
        with self._db.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM water_tanks WHERE community_id=%s",(community_id,))
            if cur.fetchone()[0]: raise ValueError("This community still has tanks. Reassign or remove its tanks first.")
            cur.execute("DELETE FROM communities WHERE community_id=%s",(community_id,))

    def resolve_alert(self, alert_id: int) -> None:
        with self._db.cursor() as cur: cur.execute("UPDATE alerts SET resolved=TRUE WHERE alert_id=%s", (alert_id,))

    def records(self, category: str) -> list[tuple[int, list[str]]]:
        with self._db.cursor() as cur:
            if category=="sensors":
                cur.execute("""SELECT s.sensor_id,s.sensor_code,s.sensor_type,w.tank_code,
                    COALESCE(r.reading_value::text || ' ' || r.reading_unit,''),COALESCE(s.status,'UNKNOWN')
                    FROM sensors s JOIN water_tanks w USING(tank_id)
                    LEFT JOIN LATERAL (SELECT reading_value,reading_unit FROM sensor_readings
                        WHERE sensor_id=s.sensor_id ORDER BY reading_time DESC,reading_id DESC LIMIT 1) r ON TRUE ORDER BY s.sensor_id""")
            elif category=="transactions":
                cur.execute("""SELECT t.transaction_id,w.tank_code,t.transaction_type,t.litres::text,
                    t.transaction_date,t.level_after::text FROM water_transactions t JOIN water_tanks w USING(tank_id)
                    ORDER BY t.transaction_date DESC""")
            elif category=="equipment":
                cur.execute("""SELECT e.equipment_id,e.equipment_name,e.equipment_type,w.tank_code,
                    COALESCE(e.status,'UNKNOWN'),COALESCE(e.installation_date::text,'')
                    FROM equipment e JOIN water_tanks w USING(tank_id) ORDER BY e.equipment_id""")
            elif category=="maintenance":
                cur.execute("""SELECT m.maintenance_id,m.maintenance_type,e.equipment_name,
                    t.first_name || ' ' || t.last_name,m.status,m.maintenance_date::text,COALESCE(m.notes,'')
                    FROM maintenance m JOIN equipment e USING(equipment_id)
                    JOIN technicians t USING(technician_id) ORDER BY m.maintenance_date DESC""")
            elif category=="technicians":
                cur.execute("""SELECT technician_id,first_name,last_name,COALESCE(phone_number,''),
                    COALESCE(email,''),COALESCE(specialisation,'') FROM technicians ORDER BY last_name,first_name""")
            elif category=="valves":
                cur.execute("""SELECT v.valve_id,v.valve_code,w.tank_code,v.valve_status,
                    COALESCE(v.installation_date::text,'') FROM valves v JOIN water_tanks w USING(tank_id) ORDER BY v.valve_id""")
            else:
                raise ValueError(f"Unsupported database records category: {category}")
            rows=[]
            for row in cur.fetchall():
                record_id,*fields=row
                fields=[value.isoformat(sep=" ") if isinstance(value,datetime) else "" if value is None else str(value) for value in fields]
                rows.append((record_id,fields))
            return rows

    def save_record(self, category: str, record_id: int, fields: list[str]) -> int:
        def tank_id(cur,code):
            cur.execute("SELECT tank_id FROM water_tanks WHERE tank_code=%s",(code.strip(),)); row=cur.fetchone()
            if not row: raise ValueError(f"Tank '{code}' does not exist.")
            return row[0]
        def save_sensor(cur):
            code,sensor_type,tank_code,reading,status=fields; target=tank_id(cur,tank_code)
            parts=reading.strip().split(maxsplit=1)
            if len(parts)!=2: raise ValueError("Enter the reading as a number and unit, for example 84 % or 12 L/min.")
            try: numeric=float(parts[0])
            except ValueError as exc: raise ValueError("Sensor reading must start with a number.") from exc
            if not math.isfinite(numeric) or numeric<0: raise ValueError("Sensor reading must be a finite, non-negative number.")
            if record_id:
                cur.execute("UPDATE sensors SET sensor_code=%s,sensor_type=%s,tank_id=%s,status=%s WHERE sensor_id=%s",(code,sensor_type,target,status,record_id))
                if not cur.rowcount: raise ValueError("Sensor no longer exists. Refresh and try again.")
                sensor_id=record_id
            else:
                cur.execute("INSERT INTO sensors(sensor_code,sensor_type,tank_id,status) VALUES(%s,%s,%s,%s) RETURNING sensor_id",(code,sensor_type,target,status)); sensor_id=cur.fetchone()[0]
            cur.execute("INSERT INTO sensor_readings(sensor_id,reading_value,reading_unit,reading_time,status) VALUES(%s,%s,%s,NOW(),%s)",(sensor_id,numeric,parts[1],status))
            return sensor_id
        if category=="sensors":
            owns_transaction=self._db.autocommit
            if owns_transaction: self._db.autocommit=False
            try:
                with self._db.cursor() as cur: saved_id=save_sensor(cur)
                if owns_transaction: self._db.commit()
                return saved_id
            except Exception:
                if owns_transaction: self._db.rollback()
                raise
            finally:
                if owns_transaction: self._db.autocommit=True
        with self._db.cursor() as cur:
            if category=="transactions":
                tank_code,kind,litres,stamp,level_after=fields; target=tank_id(cur,tank_code)
                if record_id:
                    cur.execute("UPDATE water_transactions SET tank_id=%s,transaction_type=%s,litres=%s,transaction_date=%s,level_after=%s WHERE transaction_id=%s",
                                (target,kind,litres,datetime.fromisoformat(stamp),level_after or None,record_id))
                    if cur.rowcount: return record_id
                cur.execute("INSERT INTO water_transactions(tank_id,transaction_type,litres,transaction_date,level_after) VALUES(%s,%s,%s,%s,%s) RETURNING transaction_id",
                            (target,kind,litres,datetime.fromisoformat(stamp),level_after or None)); return cur.fetchone()[0]
            if category=="equipment":
                name,kind,code,status,installed=fields; target=tank_id(cur,code); installation=date.fromisoformat(installed) if installed else None
                if record_id:
                    cur.execute("UPDATE equipment SET equipment_name=%s,equipment_type=%s,tank_id=%s,status=%s,installation_date=%s WHERE equipment_id=%s",
                                (name,kind,target,status,installation,record_id))
                    if cur.rowcount: return record_id
                cur.execute("INSERT INTO equipment(equipment_name,equipment_type,tank_id,status,installation_date) VALUES(%s,%s,%s,%s,%s) RETURNING equipment_id",
                            (name,kind,target,status,installation)); return cur.fetchone()[0]
            if category=="maintenance":
                kind,equipment_name,technician_name,status,stamp,notes=fields
                cur.execute("SELECT equipment_id FROM equipment WHERE equipment_name=%s ORDER BY equipment_id LIMIT 1",(equipment_name,)); e=cur.fetchone()
                if not e: raise ValueError(f"Equipment '{equipment_name}' does not exist.")
                cur.execute("SELECT technician_id FROM technicians WHERE first_name || ' ' || last_name=%s ORDER BY technician_id LIMIT 1",(technician_name,)); t=cur.fetchone()
                if not t: raise ValueError(f"Technician '{technician_name}' does not exist.")
                values=(t[0],e[0],kind,date.fromisoformat(stamp),notes,status)
                if record_id:
                    cur.execute("UPDATE maintenance SET technician_id=%s,equipment_id=%s,maintenance_type=%s,maintenance_date=%s,notes=%s,status=%s WHERE maintenance_id=%s",(*values,record_id))
                    if cur.rowcount: return record_id
                cur.execute("INSERT INTO maintenance(technician_id,equipment_id,maintenance_type,maintenance_date,notes,status) VALUES(%s,%s,%s,%s,%s,%s) RETURNING maintenance_id",values); return cur.fetchone()[0]
            if category=="technicians":
                first,last,phone,email,speciality=fields; values=(first,last,phone or None,email or None,speciality or None)
                if record_id:
                    cur.execute("UPDATE technicians SET first_name=%s,last_name=%s,phone_number=%s,email=%s,specialisation=%s WHERE technician_id=%s",(*values,record_id))
                    if cur.rowcount: return record_id
                cur.execute("INSERT INTO technicians(first_name,last_name,phone_number,email,specialisation) VALUES(%s,%s,%s,%s,%s) RETURNING technician_id",values); return cur.fetchone()[0]
            if category=="valves":
                code,tank_code,status,installed=fields; target=tank_id(cur,tank_code); installation=date.fromisoformat(installed) if installed else None
                if record_id:
                    cur.execute("UPDATE valves SET valve_code=%s,tank_id=%s,valve_status=%s,installation_date=%s WHERE valve_id=%s",(code,target,status,installation,record_id))
                    if cur.rowcount: return record_id
                cur.execute("INSERT INTO valves(valve_code,tank_id,valve_status,installation_date) VALUES(%s,%s,%s,%s) RETURNING valve_id",(code,target,status,installation)); return cur.fetchone()[0]
            raise ValueError(f"Unsupported database records category: {category}")

    def delete_record(self, category: str, record_id: int) -> None:
        owns_transaction=self._db.autocommit
        if owns_transaction: self._db.autocommit=False
        try:
            with self._db.cursor() as cur:
                if category=="sensors":
                    cur.execute("DELETE FROM sensor_readings WHERE sensor_id=%s",(record_id,)); cur.execute("DELETE FROM sensors WHERE sensor_id=%s",(record_id,))
                elif category=="equipment":
                    cur.execute("SELECT COUNT(*) FROM maintenance WHERE equipment_id=%s",(record_id,))
                    if cur.fetchone()[0]: raise ValueError("This equipment has maintenance history. Delete or reassign those tasks first.")
                    cur.execute("DELETE FROM equipment WHERE equipment_id=%s",(record_id,))
                elif category=="maintenance": cur.execute("DELETE FROM maintenance WHERE maintenance_id=%s",(record_id,))
                elif category=="technicians":
                    cur.execute("SELECT COUNT(*) FROM maintenance WHERE technician_id=%s",(record_id,))
                    if cur.fetchone()[0]: raise ValueError("This technician has maintenance history. Reassign those tasks before deleting the technician.")
                    cur.execute("DELETE FROM technicians WHERE technician_id=%s",(record_id,))
                elif category=="transactions": cur.execute("DELETE FROM water_transactions WHERE transaction_id=%s",(record_id,))
                elif category=="valves": cur.execute("DELETE FROM valves WHERE valve_id=%s",(record_id,))
                else: raise ValueError(f"Unsupported database records category: {category}")
            if owns_transaction: self._db.commit()
        except Exception:
            if owns_transaction: self._db.rollback()
            raise
        finally:
            if owns_transaction: self._db.autocommit=True


# --------------------------------- Styling ---------------------------------
PALETTE = {
    "navy": "#102A43", "ink": "#183B56", "muted": "#8295A6", "blue": "#1687D9",
    "aqua": "#30C7C9", "pale": "#EAF7FB", "canvas": "#F4F8FB", "line": "#E7EEF3",
    "green": "#20A879", "orange": "#E59A27", "red": "#E05B63", "white": "#FFFFFF",
}

LOGIN_USERS = ("Donald", "Michael", "Aziz", "Joshua", "Mohamed", "Alex")

APP_STYLE = f"""
QWidget {{ font-family: 'Segoe UI'; color: {PALETTE['ink']}; font-size: 13px; }}
QMainWindow, QDialog {{ background: {PALETTE['canvas']}; }}
QFrame#sidebar {{ background: {PALETTE['navy']}; border: none; }}
QFrame#card {{ background: white; border: 1px solid {PALETTE['line']}; border-radius: 14px; }}
QFrame#alertMessage {{ background: #F3F8FB; border: none; border-radius: 9px; }}
QLabel#muted {{ color: {PALETTE['muted']}; }}
QLabel#alertDetail {{ color: {PALETTE['ink']}; }}
QLabel#pageTitle {{ color: {PALETTE['navy']}; font-size: 25px; font-weight: 700; }}
QLabel#sectionTitle {{ color: {PALETTE['navy']}; font-size: 15px; font-weight: 700; }}
QPushButton {{ background: white; border: 1px solid {PALETTE['line']}; border-radius: 9px; padding: 9px 14px; font-weight: 600; }}
QPushButton:hover {{ border-color: {PALETTE['blue']}; color: {PALETTE['blue']}; }}
QPushButton#primary {{ background: {PALETTE['blue']}; color: white; border: 0; padding: 10px 16px; }}
QPushButton#primary:hover {{ background: #0874C2; color: white; }}
QPushButton#danger {{ color: #B93F49; background: #FFF2F3; border-color: #F2C9CD; padding: 7px 9px; }}
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
QFrame#alertMessage {{ background: #203444; }}
QLabel#pageTitle, QLabel#sectionTitle {{ color: #F0F6FA; }}
QLabel#muted {{ color: #9DB0BF; }}
QLabel#alertDetail {{ color: #D8E4EC; }}
QLineEdit, QComboBox, QTableWidget {{ background: #182A39; color: #E6EEF5; border-color: #294052; }}
QHeaderView::section {{ background: #203444; color: #B8C8D4; border-color: #294052; }}
QPushButton {{ background: #203444; color: #E6EEF5; border-color: #294052; }}
QPushButton#primary {{ background: {PALETTE['blue']}; color: white; }}
QPushButton#danger {{ color: #F2A0A4; background: #43282D; border-color: #613A3F; }}
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


def format_litres(value: float) -> str:
    number=float(value)
    return f"{number:,.0f}" if number.is_integer() else f"{number:,.2f}"


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
        counts=[sum(t.health==status for t in self.tanks) for status in ("Normal","Warning","Critical")]
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
    def __init__(self, communities: list[Community], status_options: list[str], tank: Optional[WaterTank] = None):
        super().__init__(); self.setWindowTitle("Tank details"); self.setMinimumWidth(440); self.tank_id = tank.asset_id if tank else 0; self.current_tank=tank
        layout = QVBoxLayout(self); layout.setSpacing(15); layout.addWidget(label("Tank information", "sectionTitle"))
        form = QFormLayout(); form.setSpacing(12)
        self.code = QLineEdit(tank.name if tank else ""); self.code.setPlaceholderText("e.g. TNK-006")
        self.community = QComboBox(); self.community.addItems([c.name for c in communities] or ["Unassigned"])
        self.capacity = QLineEdit(f"{tank.capacity:g}" if tank else "20000"); self.level = QLineEdit(f"{tank.level:g}" if tank else "0")
        self.installed=QLineEdit(tank.installed if tank else date.today().isoformat()); self.installed.setPlaceholderText("YYYY-MM-DD")
        self.status = QComboBox(); self.status.addItems(status_options)
        if tank:
            self.community.setCurrentText(tank.community); self.status.setCurrentText(tank.status)
        for title, widget in [("Tank code",self.code),("Community",self.community),("Capacity (L)",self.capacity),("Current level (L)",self.level),("Installation date",self.installed),("Database status",self.status)]: form.addRow(title,widget)
        layout.addLayout(form); buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel|QDialogButtonBox.StandardButton.Save)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def value(self) -> WaterTank:
        code = self.code.text().strip()
        if not code: raise ValueError("Enter a tank code.")
        capacity, level = float(self.capacity.text()), float(self.level.text())
        if capacity <= 0 or not 0 <= level <= capacity: raise ValueError("Capacity must be positive and water level must be within capacity.")
        installed=self.installed.text().strip()
        if installed: date.fromisoformat(installed)
        flow=self.current_tank.flow if self.current_tank else 0.0; valve=self.current_tank.valve if self.current_tank else "UNKNOWN"
        return WaterTank(self.tank_id,code,self.community.currentText(),capacity,level,flow,valve,
                         self.status.currentText(),installed=installed)


class LoginDialog(QDialog):
    """Sign-in for the six named SWIMS operators."""
    def __init__(self):
        super().__init__(); self.setWindowTitle("Sign in · SWIMS"); self.setFixedSize(440, 570)
        self.setStyleSheet("QDialog{background:#F4F8FB;} QLabel{color:#183B56;} QLineEdit{padding:13px;border:1px solid #E1EAF0;border-radius:10px;background:white;} QPushButton{padding:13px;border-radius:10px;}")
        root=QVBoxLayout(self); root.setContentsMargins(42,34,42,30); root.setSpacing(13)
        brand=QHBoxLayout(); icon=QLabel("≈"); icon.setAlignment(Qt.AlignmentFlag.AlignCenter); icon.setFixedSize(48,48); icon.setStyleSheet("background:#1687D9;color:white;border-radius:15px;font-size:34px;font-weight:bold;"); brand.addWidget(icon)
        name=QVBoxLayout(); t=QLabel("SWIMS"); t.setStyleSheet("font-size:21px;font-weight:800;letter-spacing:1px;color:#102A43;"); name.addWidget(t); sub=QLabel("SMART WATER INFRASTRUCTURE"); sub.setStyleSheet("font-size:9px;letter-spacing:1px;color:#8295A6;"); name.addWidget(sub); brand.addLayout(name); brand.addStretch(); root.addLayout(brand); root.addSpacing(18)
        art=QFrame(); art.setFixedHeight(142); art.setStyleSheet("background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #DDF5F7,stop:1 #DCEEFF);border-radius:18px;"); artlay=QVBoxLayout(art); artlay.addStretch(); wave=QLabel("     〰      〰      〰"); wave.setStyleSheet("font-size:26px;color:#1687D9;"); artlay.addWidget(wave); artlay.addWidget(QLabel("      Clean water. Connected communities.")); artlay.addStretch(); root.addWidget(art)
        welcome=QLabel("Welcome back"); welcome.setStyleSheet("font-size:22px;font-weight:700;color:#102A43;"); root.addWidget(welcome); root.addWidget(QLabel("Sign in to your water operations workspace."))
        root.addSpacing(5); root.addWidget(QLabel("Username")); self.username=QLineEdit(); self.username.setPlaceholderText("Username"); root.addWidget(self.username)
        root.addWidget(QLabel("Password")); self.password=QLineEdit(); self.password.setPlaceholderText("Enter your password"); self.password.setEchoMode(QLineEdit.EchoMode.Password); root.addWidget(self.password)
        hint=QLabel("Password format: username + 123"); hint.setAlignment(Qt.AlignmentFlag.AlignRight); hint.setStyleSheet("color:#1687D9;font-weight:600;"); root.addWidget(hint); root.addStretch()
        button=QPushButton("Sign in to SWIMS  →"); button.setStyleSheet("background:#1687D9;color:white;font-weight:700;"); button.clicked.connect(self._sign_in); root.addWidget(button)
        root.addWidget(QLabel("Secure access for authorized utility staff"),0,Qt.AlignmentFlag.AlignCenter)
    @staticmethod
    def verify_credentials(username: str, password: str) -> Optional[str]:
        canonical=next((name for name in LOGIN_USERS if name.casefold()==username.strip().casefold()),None)
        return canonical if canonical and password==canonical+"123" else None
    def _sign_in(self):
        username=self.verify_credentials(self.username.text(),self.password.text())
        if not username:
            QMessageBox.warning(self,"Sign in failed","Check the username and password, then try again."); return
        self.username.setText(username); self.accept()


# ---------------------------------- Pages ----------------------------------
class DashboardPage(QWidget):
    def __init__(self, repo: AssetRepository, username: str = "Michael"):
        super().__init__(); self.repo = repo; self.username=username
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(18)
        top = QHBoxLayout(); top.addWidget(section_heading(f"Welcome, {self.username} 👋", "Here’s what’s happening across your water network.")); top.addStretch()
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
        counts=[sum(t.health==status for t in tanks) for status in ("Normal","Warning","Critical")]
        for target,color,count in zip(self.level_legend,("Healthy","Needs attention","Critical"),counts): target.setText(f"{color} · {count}")
        values={"communities":str(len(communities)),"tanks":str(len(tanks)),"water":f"{format_litres(sum(t.level for t in tanks))} L","alerts":str(sum(not a.resolved for a in alerts))}
        for widget,key in self._metric_cards: widget.setText(values[key])
        while self.alert_list.count():
            item=self.alert_list.takeAt(0); w=item.widget()
            if w: w.deleteLater()
        for alert in [a for a in alerts if not a.resolved][:3]:
            row=QHBoxLayout(); dot=label("●"); color=PALETTE["red"] if alert.severity=="Critical" else PALETTE["orange"] if alert.severity=="Warning" else PALETTE["blue"]; dot.setStyleSheet(f"color:{color};"); row.addWidget(dot); col=QVBoxLayout(); col.addWidget(label(alert.title)); col.addWidget(label(f"{alert.tank}  ·  {alert.time}","muted")); row.addLayout(col,1); self.alert_list.addLayout(row)


class TanksPage(QWidget):
    def __init__(self, repo: AssetRepository, changed):
        super().__init__(); self.repo,self.changed=repo,changed; root=QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(14)
        self.status_options=["ACTIVE","MAINTENANCE"] if isinstance(repo,PostgresRepository) else ["Normal","Warning","Critical"]
        head=QHBoxLayout(); head.addWidget(section_heading("Tank management","Monitor levels, flow and connected equipment.")); head.addStretch(); self.search=QLineEdit(); self.search.setPlaceholderText("⌕  Search tanks..."); self.search.setMaximumWidth(220); self.filter=QComboBox(); self.filter.addItem("All communities"); self.filter.addItems([c.name for c in repo.communities()]); add=make_button("＋  Add tank",True); add.clicked.connect(self.add_tank); head.addWidget(self.search); head.addWidget(self.filter); head.addWidget(add); root.addLayout(head)
        summary=QHBoxLayout()
        self.summary_values=[]
        for text,detail,color in [("0 connected","All network tanks",PALETTE["blue"]),("0% average","Network fill level",PALETTE["green"]),("0 critical","Immediate follow-up",PALETTE["red"])]:
            f=card(); l=QVBoxLayout(f); l.setContentsMargins(15,12,15,12); v=label(text); v.setStyleSheet(f"font-size:17px;font-weight:700;color:{color};"); l.addWidget(v); l.addWidget(label(detail,"muted")); summary.addWidget(f); self.summary_values.append(v)
        root.addLayout(summary)
        self.table=QTableWidget(0,7); self.table.setHorizontalHeaderLabels(["TANK / COMMUNITY","LEVEL","CAPACITY","FLOW","VALVE","STATUS","ACTIONS"]); self.table.verticalHeader().setVisible(False); self.table.setShowGrid(False); self.table.setAlternatingRowColors(True); self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows); self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); self.table.setWordWrap(False); self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter); self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch); self.table.horizontalHeader().setSectionResizeMode(6,QHeaderView.ResizeMode.Fixed); self.table.horizontalHeader().resizeSection(6,164)
        root.addWidget(self.table,1); self.search.textChanged.connect(self.refresh); self.filter.currentTextChanged.connect(self.refresh); self.refresh()

    def refresh(self):
        query=self.search.text().lower(); community=self.filter.currentText(); tanks=[t for t in self.repo.tanks() if (not query or query in t.name.lower() or query in t.community.lower()) and (community=="All communities" or t.community==community)]
        all_tanks=self.repo.tanks(); average=round(sum(t.percentage for t in all_tanks)/len(all_tanks)) if all_tanks else 0
        for widget,value in zip(self.summary_values,(f"{len(all_tanks):02d} connected",f"{average}% average",f"{sum(t.health=='Critical' for t in all_tanks):02d} critical")): widget.setText(value)
        self.table.setRowCount(len(tanks))
        for r,t in enumerate(tanks):
            c=QWidget(); cl=QVBoxLayout(c); cl.setContentsMargins(8,5,8,5); cl.addWidget(label(t.name)); cl.addWidget(label(f"{t.community} · Updated {t.updated}","muted")); self.table.setCellWidget(r,0,c)
            bar=QWidget(); bl=QVBoxLayout(bar); bl.setContentsMargins(8,10,8,10); pct=label(f"{t.percentage}%"); pct.setStyleSheet(f"color:{PALETTE['red'] if t.percentage<30 else PALETTE['orange'] if t.percentage<50 else PALETTE['green']};font-weight:700;"); bl.addWidget(pct); self.table.setCellWidget(r,1,bar)
            self.table.setItem(r,2,QTableWidgetItem(f"{format_litres(t.capacity)} L")); self.table.setItem(r,3,QTableWidgetItem(f"{t.flow:g} L/min")); self.table.setItem(r,4,QTableWidgetItem("●  "+t.valve))
            badge=QLabel("  "+t.status.replace("_"," ").title()+"  "); color=PALETTE["green"] if t.health=="Normal" else PALETTE["orange"] if t.health=="Warning" else PALETTE["red"]; badge.setStyleSheet(f"color:{color};background:#18{color[1:]};border-radius:8px;padding:5px;font-weight:600;"); badge.setAlignment(Qt.AlignmentFlag.AlignCenter); self.table.setCellWidget(r,5,badge)
            actions=QWidget(); ar=QHBoxLayout(actions); ar.setContentsMargins(3,4,3,4); ar.setSpacing(5); edit=QPushButton("Edit"); delete=QPushButton("Delete"); edit.setMinimumWidth(56); delete.setMinimumWidth(72); delete.setObjectName("danger"); edit.clicked.connect(lambda checked=False,x=t:self.edit_tank(x)); delete.clicked.connect(lambda checked=False,x=t:self.delete_tank(x)); ar.addWidget(edit); ar.addWidget(delete); self.table.setCellWidget(r,6,actions); self.table.setRowHeight(r,62)

    def add_tank(self):
        dlg=TankDialog(self.repo.communities(),self.status_options)
        if dlg.exec():
            try:
                tank=self.repo.save_tank(dlg.value()); self._show_tank(tank); self.changed()
            except Exception as exc: QMessageBox.warning(self,"Could not save tank",str(exc))
    def edit_tank(self,tank):
        dlg=TankDialog(self.repo.communities(),self.status_options,tank)
        if dlg.exec():
            try:
                tank=self.repo.save_tank(dlg.value()); self._show_tank(tank); self.changed()
            except Exception as exc: QMessageBox.warning(self,"Could not save tank",str(exc))
    def _show_tank(self,tank):
        self.search.blockSignals(True); self.filter.blockSignals(True)
        self.search.clear(); self.filter.setCurrentIndex(0)
        self.search.blockSignals(False); self.filter.blockSignals(False)
        self.refresh()
        for row,current in enumerate(self.repo.tanks()):
            if current.asset_id==tank.asset_id:
                self.table.selectRow(row); self.table.scrollToItem(self.table.item(row,2)); break
    def delete_tank(self,tank):
        if QMessageBox.question(self,"Delete tank",f"Delete {tank.name} and its linked sensors, readings, valves, transactions, alerts, equipment and maintenance records? This cannot be undone.")==QMessageBox.StandardButton.Yes:
            try: self.repo.delete_tank(tank.asset_id); self.refresh(); self.changed()
            except Exception as exc: QMessageBox.critical(self,"Delete failed",str(exc))


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
        self.table=QTableWidget(0,5)
        self.table.setHorizontalHeaderLabels(["COMMUNITY","LOCATION","TANKS","HOUSEHOLDS","ACTIONS"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4,QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().resizeSection(4,164)
        layout.addWidget(self.table)
        root.addWidget(frame,1)
        self.search.textChanged.connect(self._filter); self.refresh()
    def refresh(self):
        communities=self.repo.communities(); self.table.setRowCount(len(communities))
        for row,item in enumerate(communities):
            values=[item.name,item.location,str(item.tanks),f"{item.households:,}"]
            for col,value in enumerate(values): self.table.setItem(row,col,QTableWidgetItem(value))
            cell=QWidget(); cell_layout=QHBoxLayout(cell); cell_layout.setContentsMargins(4,4,4,4); cell_layout.setSpacing(6)
            edit=QPushButton("Edit"); delete=QPushButton("Delete"); edit.setMinimumWidth(56); delete.setMinimumWidth(72); delete.setObjectName("danger"); edit.clicked.connect(lambda checked=False,c=item:self.edit_community(c)); delete.clicked.connect(lambda checked=False,c=item:self.delete_community(c)); cell_layout.addWidget(edit); cell_layout.addWidget(delete); self.table.setCellWidget(row,4,cell); self.table.setRowHeight(row,56)
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
        if QMessageBox.question(self,"Delete community",f"Delete {community.name}? Reassign or delete its tanks first.")==QMessageBox.StandardButton.Yes:
            try: self.repo.delete_community(community.community_id); self.refresh(); self.changed()
            except Exception as exc: QMessageBox.critical(self,"Delete failed",str(exc))


class GenericRecordDialog(QDialog):
    """Consistent validated form used by database-backed operations lists."""
    def __init__(self, title: str, headers: tuple[str, ...], values: Optional[list[str]] = None,
                 required_fields: tuple[int, ...] = (), choices: Optional[dict[int,list[str]]] = None):
        super().__init__(); self.setWindowTitle(title); self.setMinimumWidth(440)
        self.fields: list[QWidget] = []; self.required_fields=required_fields; choices=choices or {}
        root=QVBoxLayout(self); root.setContentsMargins(24,22,24,18); root.setSpacing(16)
        root.addWidget(label(title,"sectionTitle")); form=QFormLayout(); form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow); form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter); form.setHorizontalSpacing(18); form.setVerticalSpacing(12)
        for index, header in enumerate(headers):
            current=values[index] if values and index<len(values) else ""
            if index in choices:
                field=QComboBox(); field.setMinimumWidth(250); field.addItems(choices[index]); field.setCurrentText(current)
                if current and field.currentText()!=current: field.addItem(current); field.setCurrentText(current)
            else:
                field=QLineEdit(current); field.setMinimumWidth(250)
                hint="YYYY-MM-DD" if "date" in header.lower() else "e.g. 84 % or 12 L/min" if "reading" in header.lower() else f"Enter {header.lower()}"
                field.setPlaceholderText(hint)
            form.addRow(header,field); self.fields.append(field)
        root.addLayout(form); buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel|QDialogButtonBox.StandardButton.Save)
        buttons.accepted.connect(self._validate); buttons.rejected.connect(self.reject); root.addWidget(buttons)
    def _validate(self):
        if any(index>=len(self.fields) or not self._text(self.fields[index]).strip() for index in self.required_fields):
            QMessageBox.warning(self,"Required fields", "Complete all required fields before saving this record."); return
        self.accept()
    @staticmethod
    def _text(field: QWidget) -> str:
        return field.currentText() if isinstance(field,QComboBox) else field.text()
    def value(self) -> list[str]: return [self._text(field).strip() for field in self.fields]


class SettingsPage(QWidget):
    def __init__(self, theme_changed, username: str, logout):
        super().__init__(); root=QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(16)
        root.addWidget(section_heading("Profile & settings","Manage your operator account and application preferences."))
        account=card(); al=QVBoxLayout(account); al.setContentsMargins(20,18,20,18); al.addWidget(label("Operator profile","sectionTitle")); al.addWidget(label(f"{username} · System operator")); al.addWidget(label(f"{username.lower()}@swims.local","muted")); root.addWidget(account)
        prefs=card(); pl=QVBoxLayout(prefs); pl.setContentsMargins(20,18,20,18); pl.addWidget(label("Preferences","sectionTitle")); self.dark=QCheckBox("Use dark appearance"); self.dark.toggled.connect(theme_changed); pl.addWidget(self.dark); notifications=QCheckBox("Receive critical alert notifications"); notifications.setChecked(True); pl.addWidget(notifications); root.addWidget(prefs)
        self.logout_button=make_button("Log out"); self.logout_button.setObjectName("danger"); self.logout_button.clicked.connect(logout); root.addWidget(self.logout_button,0,Qt.AlignmentFlag.AlignLeft); root.addStretch()


class ReportsPage(QWidget):
    def __init__(self, repo: AssetRepository):
        super().__init__(); self.repo=repo; root=QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(16)
        heading=QHBoxLayout(); heading.addWidget(section_heading("Reports & exports","Build clear reports from your saved water operations data.")); heading.addStretch(); root.addLayout(heading)
        self.summary_values=[]; summary=QHBoxLayout(); summary.setSpacing(12)
        for title,color in [("Tanks",PALETTE["blue"]),("Transactions",PALETTE["aqua"]),("Open alerts",PALETTE["red"]),("Maintenance tasks",PALETTE["orange"])]:
            frame=card(); layout=QVBoxLayout(frame); layout.setContentsMargins(16,12,16,12); layout.addWidget(label(title,"muted")); value=label("0"); value.setStyleSheet(f"font-size:24px;font-weight:700;color:{color};"); layout.addWidget(value); summary.addWidget(frame); self.summary_values.append(value)
        root.addLayout(summary)
        root.addWidget(section_heading("Available reports","Choose PDF for a print-ready summary or Excel for data analysis."))
        self.grid=QGridLayout(); self.grid.setHorizontalSpacing(14); self.grid.setVerticalSpacing(14); root.addLayout(self.grid,1)
        self.report_rows=[
            ("Water usage","Transaction volumes, types, and timestamps","usage","↕"),
            ("Tank status","Water levels, capacity, valves, and sensor flow","tanks","◉"),
            ("Alerts & incidents","Alert messages, priority, and resolution state","alerts","!"),
            ("Maintenance history","Field tasks, technicians, dates, and notes","maintenance","⚙"),
        ]
        self.report_counts={}
        for index,(title,description,category,icon_text) in enumerate(self.report_rows):
            frame=card(); box=QVBoxLayout(frame); box.setContentsMargins(18,16,18,16); box.setSpacing(10)
            head=QHBoxLayout(); icon=label(icon_text); icon.setAlignment(Qt.AlignmentFlag.AlignCenter); icon.setFixedSize(38,38); icon.setStyleSheet("background:#EAF7FB;color:#1687D9;border-radius:11px;font-size:18px;font-weight:700;"); head.addWidget(icon); head.addWidget(label(title,"sectionTitle"),1); box.addLayout(head)
            detail=label(description,"muted"); detail.setWordWrap(True); detail.setMinimumHeight(38); box.addWidget(detail)
            foot=QHBoxLayout(); count=label("0 records","muted"); foot.addWidget(count); foot.addStretch()
            for format_name in ("PDF","Excel"):
                button=make_button(format_name); button.clicked.connect(lambda checked=False,c=category,f=format_name:self.export(c,f)); foot.addWidget(button)
            box.addLayout(foot); self.grid.addWidget(frame,index//2,index%2); self.report_counts[category]=count
        self.refresh()
    def _data_for(self,category):
        if category=="usage":
            return RECORD_SCHEMAS["transactions"],[fields for _,fields in self.repo.records("transactions")],"water_usage"
        if category=="maintenance":
            return RECORD_SCHEMAS["maintenance"],[fields for _,fields in self.repo.records("maintenance")],"maintenance"
        if category=="tanks":
            headers=("Tank code","Community","Capacity (L)","Current level (L)","Percentage","Flow (L/min)","Valve","Status")
            rows=[[tank.name,tank.community,tank.capacity,tank.level,tank.percentage,tank.flow,tank.valve,tank.status] for tank in self.repo.tanks()]
            return headers,rows,"tank_status"
        headers=("Alert","Tank","Severity","Time","Details","Resolved")
        rows=[[alert.title,alert.tank,alert.severity,alert.time,alert.detail,"Yes" if alert.resolved else "No"] for alert in self.repo.alerts()]
        return headers,rows,"alerts"
    def refresh(self):
        tanks=self.repo.tanks(); transactions=self.repo.records("transactions"); alerts=self.repo.alerts(); maintenance=self.repo.records("maintenance")
        counts=(len(tanks),len(transactions),sum(not alert.resolved for alert in alerts),len(maintenance))
        for widget,value in zip(self.summary_values,counts): widget.setText(str(value))
        for _,_,category,_ in self.report_rows:
            _,rows,_=self._data_for(category); self.report_counts[category].setText(f"{len(rows)} record"+("s" if len(rows)!=1 else ""))
    def export(self,category,format_name):
        headers,rows,name=self._data_for(category)
        if format_name=="Excel":
            path,_=QFileDialog.getSaveFileName(self,"Export Excel report",f"swims_{name}.xlsx","Excel workbook (*.xlsx)")
            if not path: return
            if not path.lower().endswith(".xlsx"): path+=".xlsx"
            try:
                from openpyxl import Workbook
                from openpyxl.styles import Alignment,Font,PatternFill
                workbook=Workbook(); sheet=workbook.active; sheet.title=name[:31]
                sheet.append([next(title for title,_,key,_ in self.report_rows if key==category)]); sheet.merge_cells(start_row=1,start_column=1,end_row=1,end_column=len(headers))
                sheet["A1"].font=Font(bold=True,size=16,color="102A43"); sheet.append(list(headers))
                for cell in sheet[2]: cell.font=Font(bold=True,color="FFFFFF"); cell.fill=PatternFill("solid",fgColor="1687D9"); cell.alignment=Alignment(vertical="center")
                for row in rows: sheet.append(list(row))
                sheet.freeze_panes="A3"; sheet.auto_filter.ref=sheet.dimensions
                from openpyxl.utils import get_column_letter
                for index,header in enumerate(headers,1):
                    values=[str(header),*(str(row[index-1] or "") for row in rows)]
                    sheet.column_dimensions[get_column_letter(index)].width=min(42,max(14,max(map(len,values))+2))
                workbook.save(path)
            except Exception as exc: QMessageBox.critical(self,"Excel export failed",f"{exc}\n\nInstall dependencies with: py -m pip install -r requirements.txt"); return
        else:
            path,_=QFileDialog.getSaveFileName(self,"Export PDF report",f"swims_{name}.pdf","PDF document (*.pdf)")
            if not path: return
            if not path.lower().endswith(".pdf"): path+=".pdf"
            try:
                from reportlab.lib import colors
                from reportlab.lib.enums import TA_LEFT
                from reportlab.lib.pagesizes import A4,landscape
                from reportlab.lib.styles import ParagraphStyle,getSampleStyleSheet
                from reportlab.lib.units import mm
                from reportlab.platypus import Paragraph,SimpleDocTemplate,Spacer,Table,TableStyle
                title=next(title for title,_,key,_ in self.report_rows if key==category)
                doc=SimpleDocTemplate(path,pagesize=landscape(A4),rightMargin=15*mm,leftMargin=15*mm,topMargin=15*mm,bottomMargin=15*mm)
                styles=getSampleStyleSheet(); story=[Paragraph("SWIMS · "+escape(title),styles["Title"]),Paragraph("Smart Water Infrastructure Management System · Generated "+datetime.now().strftime("%Y-%m-%d %H:%M"),styles["Normal"]),Spacer(1,8*mm)]
                body=ParagraphStyle("SWIMSBody",parent=styles["BodyText"],fontSize=8,leading=11,alignment=TA_LEFT)
                table_data=[[Paragraph(escape(str(value)),body) for value in headers]]+[[Paragraph(escape(str(value)),body) for value in row] for row in rows]
                table=Table(table_data,repeatRows=1,hAlign="LEFT")
                table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#102A43")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("GRID",(0,0),(-1,-1),0.35,colors.HexColor("#D9E3EA")),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F3F8FB")]),("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),7),("RIGHTPADDING",(0,0),(-1,-1),7),("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6)]))
                story.append(table); doc.build(story)
            except Exception as exc: QMessageBox.critical(self,"PDF export failed",f"{exc}\n\nInstall dependencies with: py -m pip install -r requirements.txt"); return
        QMessageBox.information(self,"Export complete",f"Report saved to:\n{path}")


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
        self.table.horizontalHeader().setSectionResizeMode(len(headers),QHeaderView.ResizeMode.Fixed); self.table.horizontalHeader().resizeSection(len(headers),164)
        card_layout.addWidget(self.table); root.addWidget(table_card,1)
        self.search.textChanged.connect(self._filter); self.refresh()
    def refresh(self):
        rows=self.repo.records(self.category); self.table.setRowCount(len(rows))
        for row,(record_id,fields) in enumerate(rows):
            for column,value in enumerate(fields):
                item=QTableWidgetItem(str(value)); item.setData(Qt.ItemDataRole.UserRole,record_id); self.table.setItem(row,column,item)
            actions=QWidget(); actions.setObjectName("tableActions"); actions_layout=QHBoxLayout(actions); actions_layout.setContentsMargins(3,4,3,4); actions_layout.setSpacing(5)
            edit=QPushButton("Edit"); delete=QPushButton("Delete"); edit.setMinimumWidth(56); delete.setMinimumWidth(72); delete.setObjectName("danger"); edit.clicked.connect(lambda checked=False,i=record_id,f=list(fields):self.edit_record(i,f)); delete.clicked.connect(lambda checked=False,i=record_id:self.delete_record(i)); actions_layout.addWidget(edit); actions_layout.addWidget(delete)
            self.table.setCellWidget(row,len(self.headers),actions); self.table.setRowHeight(row,56)
        self._filter(self.search.text())
    def _filter(self,query):
        query=query.casefold()
        for row in range(self.table.rowCount()):
            match=any(query in (self.table.item(row,col).text().casefold() if self.table.item(row,col) else "") for col in range(len(self.headers)))
            self.table.setRowHidden(row,bool(query) and not match)
    def add_record(self):
        dialog=GenericRecordDialog(f"Add {self.title.rstrip('s').lower()}",self.headers,required_fields=REQUIRED_RECORD_FIELDS[self.category],choices=self._choices())
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self._save(0,dialog.value())
    def edit_record(self,record_id,values):
        dialog=GenericRecordDialog(f"Edit {self.title.rstrip('s').lower()}",self.headers,values,REQUIRED_RECORD_FIELDS[self.category],self._choices())
        if dialog.exec()==QDialog.DialogCode.Accepted: self._save(record_id,dialog.value())
    def _choices(self):
        tanks=[tank.name for tank in self.repo.tanks()]
        if self.category=="sensors": return {2:tanks,4:["ACTIVE","INACTIVE","FAULT"]}
        if self.category=="equipment": return {2:tanks,3:["OPERATIONAL","MAINTENANCE","FAULTY"]}
        if self.category=="transactions": return {0:tanks,1:["INFLOW","USAGE"]}
        if self.category=="valves": return {1:tanks,2:["OPEN","CLOSED","FAULT"]}
        if self.category=="maintenance":
            equipment=[fields[0] for _,fields in self.repo.records("equipment")]
            technicians=[f"{fields[0]} {fields[1]}" for _,fields in self.repo.records("technicians")]
            return {1:equipment,2:technicians,3:["Scheduled","In Progress","Completed"]}
        return {}
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
        super().__init__(); self.repo=repo; root=QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(16); top=QHBoxLayout(); top.addWidget(section_heading("Alerts & incidents","Review the full alert message, affected tank, and resolution status.")); top.addStretch(); root.addLayout(top)
        self.scroll=QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.Shape.NoFrame); self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_host=QWidget(); self.list=QVBoxLayout(self.list_host); self.list.setContentsMargins(2,2,10,2); self.list.setSpacing(12); self.scroll.setWidget(self.list_host); root.addWidget(self.scroll,1); self.refresh()
    def refresh(self):
        while self.list.count():
            item=self.list.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        for a in self.repo.alerts():
            frame=card(); frame.setMinimumHeight(118); row=QHBoxLayout(frame); row.setContentsMargins(16,14,16,14); row.setSpacing(14)
            col=PALETTE["red"] if a.severity=="Critical" else PALETTE["orange"] if a.severity=="Warning" else PALETTE["blue"]
            icon=label("!"); icon.setAlignment(Qt.AlignmentFlag.AlignCenter); icon.setFixedSize(38,38); icon.setStyleSheet(f"color:{col};background:#18{col[1:]};border-radius:12px;font-size:17px;font-weight:700;"); row.addWidget(icon,0,Qt.AlignmentFlag.AlignTop)
            content=QVBoxLayout(); content.setSpacing(6); title=label(a.title); title.setStyleSheet("font-size:14px;font-weight:700;color:#102A43;"); content.addWidget(title)
            content.addWidget(label(f"{a.tank}   ·   {a.time}","muted"))
            message=QFrame(); message.setObjectName("alertMessage"); message_layout=QVBoxLayout(message); message_layout.setContentsMargins(11,8,11,8)
            detail=label(a.detail,"alertDetail"); detail.setWordWrap(True); detail.setMinimumWidth(280); detail.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred); message_layout.addWidget(detail); content.addWidget(message); row.addLayout(content,1)
            actions=QVBoxLayout(); actions.setSpacing(10); badge=label("Resolved" if a.resolved else a.severity); badge.setAlignment(Qt.AlignmentFlag.AlignCenter); badge.setStyleSheet(f"color:{col};background:#18{col[1:]};border-radius:9px;padding:7px 9px;font-size:11px;font-weight:700;"); actions.addWidget(badge,0,Qt.AlignmentFlag.AlignRight)
            if not a.resolved:
                button=make_button("Mark resolved"); button.clicked.connect(lambda checked=False,x=a:self.resolve(x)); actions.addWidget(button,0,Qt.AlignmentFlag.AlignRight)
            actions.addStretch(); row.addLayout(actions); self.list.addWidget(frame)
        self.list.addStretch(1)
    def resolve(self,alert):
        try: self.repo.resolve_alert(alert.alert_id); self.refresh()
        except Exception as exc: QMessageBox.critical(self,"Could not resolve alert",str(exc))


class SwimsWindow(QMainWindow):
    def __init__(self, repo: AssetRepository, demo: bool, username: str = "Michael"):
        super().__init__(); self.repo=repo; self.demo=demo; self.username=username; self.setWindowTitle("SWIMS · Smart Water Infrastructure Management System")
        available=QApplication.primaryScreen().availableGeometry(); width=max(900,min(1440,available.width()-32)); height=max(620,min(900,available.height()-48))
        self.setMinimumSize(min(980,width),min(660,height)); self.resize(width,height)
        shell=QWidget(); self.setCentralWidget(shell); outer=QHBoxLayout(shell); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        sidebar=QFrame(); sidebar.setObjectName("sidebar"); sidebar.setFixedWidth(226); sl=QVBoxLayout(sidebar); sl.setContentsMargins(15,22,15,16); sl.setSpacing(5)
        brand=QHBoxLayout(); mark=QLabel("≈"); mark.setAlignment(Qt.AlignmentFlag.AlignCenter); mark.setFixedSize(38,38); mark.setStyleSheet("background:#1687D9;color:white;border-radius:12px;font-size:27px;font-weight:700;"); brand.addWidget(mark); names=QVBoxLayout(); n=QLabel("SWIMS"); n.setStyleSheet("color:white;font-size:17px;font-weight:800;letter-spacing:1px;"); names.addWidget(n); sub=QLabel("WATER OPERATIONS"); sub.setStyleSheet("color:#91A9BB;font-size:8px;letter-spacing:1px;"); names.addWidget(sub); brand.addLayout(names); brand.addStretch(); sl.addLayout(brand); sl.addSpacing(26)
        cap=QLabel("WORKSPACE"); cap.setStyleSheet("color:#7891A5;font-size:9px;font-weight:700;letter-spacing:1.2px;padding-left:12px;"); sl.addWidget(cap); sl.addSpacing(7)
        self.stack=QStackedWidget(); self.nav_buttons=[]; self.pages=[]
        names=[("⌂","Dashboard"),("▤","Communities"),("◉","Tank management"),("◌","Sensors"),("!","Alerts"),("↕","Transactions"),("⚙","Equipment"),("◍","Valves"),("▣","Maintenance"),("♙","Technicians"),("▥","Reports"),("●","Profile & settings")]
        for icon,title in names:
            b=QPushButton(f"{icon}    {title}"); b.setObjectName("nav"); b.setProperty("selected",title=="Dashboard"); b.clicked.connect(lambda checked=False,x=title:self.navigate(x)); sl.addWidget(b); self.nav_buttons.append((title,b))
        sl.addStretch(); profile=QFrame(); profile.setStyleSheet("background:#1B3A53;border-radius:12px;"); pl=QHBoxLayout(profile); pl.setContentsMargins(10,10,10,10); avatar=QLabel(username[:2].upper()); avatar.setAlignment(Qt.AlignmentFlag.AlignCenter); avatar.setFixedSize(34,34); avatar.setStyleSheet("background:#2E607D;color:white;border-radius:17px;font-weight:700;"); pl.addWidget(avatar); ptxt=QVBoxLayout(); pn=QLabel(username); pn.setStyleSheet("color:white;font-size:11px;font-weight:600;"); pr=QLabel("System operator"); pr.setStyleSheet("color:#91A9BB;font-size:10px;"); ptxt.addWidget(pn); ptxt.addWidget(pr); pl.addLayout(ptxt); sl.addWidget(profile); outer.addWidget(sidebar)
        body=QWidget(); bl=QVBoxLayout(body); bl.setContentsMargins(27,20,27,20); bl.setSpacing(18)
        top=QHBoxLayout(); breadcrumb=QLabel("Operations  /  <b>Dashboard</b>"); breadcrumb.setStyleSheet("color:#8295A6;"); top.addWidget(breadcrumb); top.addStretch(); self.conn=QLabel("●  DEMO DATA" if demo else "●  POSTGRESQL CONNECTED"); self.conn.setStyleSheet("color:#14835F;background:#E5F6EF;border-radius:9px;padding:7px 10px;font-size:10px;font-weight:700;"); top.addWidget(self.conn); self.theme_button=QPushButton("◐  Dark mode"); self.theme_button.setCheckable(True); self.theme_button.toggled.connect(self.toggle_theme); top.addWidget(self.theme_button); bell=QPushButton("♧  3"); bell.clicked.connect(lambda:self.navigate("Alerts")); top.addWidget(bell); bl.addLayout(top)
        self.page_stack=QStackedWidget(); bl.addWidget(self.page_stack,1); outer.addWidget(body,1); self.breadcrumb=breadcrumb
        self.dashboard=DashboardPage(repo,username); self.dashboard.view_all_button.clicked.connect(lambda:self.navigate("Alerts")); self.tanks=TanksPage(repo,self.refresh_dashboard); self.alerts=AlertsPage(repo)
        profile=SettingsPage(self.toggle_theme,username,self.logout); self.settings=profile
        self.page_map={"Dashboard":self.dashboard,
            "Communities":CommunityPage(repo,self.community_changed),
            "Tank management":self.tanks,
            "Sensors":GenericPage(repo,"sensors","Sensor monitoring","Live health and readings from connected field devices.",RECORD_SCHEMAS["sensors"]),
            "Alerts":self.alerts,
            "Transactions":GenericPage(repo,"transactions","Water transactions","Inflow and consumption records from across the network.",RECORD_SCHEMAS["transactions"]),
            "Equipment":GenericPage(repo,"equipment","Equipment","Pumps, valves, flow meters and control units.",RECORD_SCHEMAS["equipment"]),
            "Valves":GenericPage(repo,"valves","Valves","Manage valve status and installation records.",RECORD_SCHEMAS["valves"]),
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
        if title=="Tank management": self.tanks.refresh()
        if title=="Communities": self.page_map[title].refresh()
        if isinstance(self.page_map[title],GenericPage): self.page_map[title].refresh()
        if title=="Reports": self.page_map[title].refresh()
    def logout(self):
        self.hide()
        login=LoginDialog()
        if login.exec()==QDialog.DialogCode.Accepted:
            self.next_window=SwimsWindow(self.repo,self.demo,login.username.text())
            self.next_window.show()
        self.close()
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


def load_local_environment(path: Optional[Path] = None) -> None:
    """Read simple KEY=VALUE entries; process-level variables take precedence."""
    path=path or Path(__file__).resolve().parent/".env"
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
        QMessageBox.critical(None,"Database connection failed",f"SWIMS could not connect to the configured PostgreSQL schema.\n\n{exc}\n\nCheck DB_* values in .env and confirm the database is available."); return 1
    login=LoginDialog()
    if login.exec()!=QDialog.DialogCode.Accepted: return 0
    window=SwimsWindow(repo,demo,login.username.text()); window.show(); return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
