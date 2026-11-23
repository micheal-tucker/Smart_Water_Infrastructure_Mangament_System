# SWIMS — Smart Water Infrastructure Management System

A Python and PyQt6 desktop dashboard for monitoring community water assets. The screens use a responsive, card-based layout with water-level visuals, operations summaries, live-style readings, alerts, maintenance activity, and a light/dark theme.

## Run the application

1. Install Python 3.10 or newer.
2. In this folder, install the dependencies:

   ```powershell
   py -m pip install -r requirements.txt
   ```

3. Start the application:

   ```powershell
   py main.py
   ```

Without a database connection setting, SWIMS opens with clearly labelled sample data. Sign in with one of these operator usernames and use the username followed by `123` as the password: `Donald`, `Michael`, `Aziz`, `Joshua`, `Mohamed`, or `Alex`. Usernames are case-insensitive.

## PostgreSQL setup

Create a PostgreSQL database (for example, `swims`). Put its settings in a local `.env` file in this folder:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
py main.py
```

Fill in `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`. The app reads `.env` automatically; process environment variables override values from the file. You can also use `SWIMS_DATABASE_URL` if you prefer a connection URL. `.env` is ignored by Git so database credentials are not committed.

SWIMS uses the restored database tables directly: `communities`, `water_tanks`, `sensors`, `sensor_readings`, `valves`, `water_transactions`, `equipment`, `maintenance`, `technicians`, and `alerts`. It checks the required columns at startup instead of creating duplicate tables. The assignment needs a maintenance status, so startup adds a `status` column to `maintenance` if it is missing. Tank and community changes, sensor readings, valves, transactions, equipment, maintenance, and technicians are written to their corresponding PostgreSQL tables. Reports export print-ready PDF files and formatted Excel workbooks.

The app's **DEMO DATA** mode uses in-memory sample data. Changes made in demo mode disappear when the app closes. Use the PostgreSQL connection setting above whenever you need saved data.

The requested operator credentials are checked by the desktop application and are intended for the assignment demonstration; they are not a secure production authentication system. Sensor values are operator-managed records; this project does not connect to an ESP32 or ingest live IoT messages yet.

## Assignment brief mapping

- **Python OOP:** `WaterAsset` is an abstract base class; `WaterTank`, `Sensor`, and `Equipment` override `summary()` and demonstrate inheritance and polymorphism. `WaterTank` encapsulates capacity, level, and status with properties. `Community` and `Alert` use dataclasses.
- **Classes and objects:** domain objects are created from repository records and passed to PyQt6 screens.
- **Data structures:** lists of domain objects drive the community, tank, and alert views; filtering/search updates displayed records.
- **GUI:** all screens and charts are native PyQt6 widgets; no JavaScript, web UI, or React Native runtime is used.
- **Database:** `AssetRepository` defines the storage interface. `DemoRepository` supports offline demonstrations; `PostgresRepository` provides PostgreSQL persistence using psycopg2 and parameterized statements.
- **CRUD:** tank and community screens plus sensor, transaction, equipment, maintenance, and technician lists provide validated add/edit/delete flows backed by the selected repository. Alerts can be marked resolved. The reports screen exports styled PDF and Excel reports for water usage, tank status, alerts, and maintenance.
- **DPG-minded design:** readable status labels supplement color, form validation protects data, and the layout keeps operational information clear and accessible.

## Project structure

```text
main.py          PyQt6 interface, domain model, repositories, and application entry point
requirements.txt Runtime dependencies
.env.example     PostgreSQL connection setting example
```

Dashboard charts and activity summaries are currently illustrative. A production IoT deployment would connect the sensor records to a live ingestion service and add authenticated user accounts and audit logging.
