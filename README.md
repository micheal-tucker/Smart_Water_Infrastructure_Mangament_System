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

Without a database connection setting, SWIMS opens with clearly labelled sample data. The sign-in screen is a UI prototype: any non-empty email and password opens the dashboard; it does not authenticate users.

## PostgreSQL setup

Create a PostgreSQL database (for example, `swims`) and set the connection string before starting the app:

```powershell
$env:SWIMS_DATABASE_URL = "postgresql://postgres:your-password@localhost:5432/swims"
py main.py
```

On first connection the app creates the `communities`, `tanks`, `alerts`, and `swims_records` tables. It inserts four starter communities only when the communities table is empty. Tanks, sensors, water transactions, equipment, maintenance tasks, and technicians each have working add, edit, delete, search, and CSV export controls. Tank and community changes, alert resolution, and operational records are written to PostgreSQL immediately. Reports export the current tank, alert, transaction, or maintenance data to CSV, which opens in Excel. A newly created database has no tanks or operational records; add them from the corresponding screens.

The app's **DEMO DATA** mode uses in-memory sample data. Changes made in demo mode disappear when the app closes. Use the PostgreSQL connection setting above whenever you need saved data.

The sign-in screen is still a presentation prototype and accepts any non-empty credentials. It is not authentication and should not be used to protect a deployed system. Sensor values are operator-managed records; this project does not connect to an ESP32 or ingest live IoT messages yet.

## Assignment brief mapping

- **Python OOP:** `WaterAsset` is an abstract base class; `WaterTank`, `Sensor`, and `Equipment` override `summary()` and demonstrate inheritance and polymorphism. `WaterTank` encapsulates capacity, level, and status with properties. `Community` and `Alert` use dataclasses.
- **Classes and objects:** domain objects are created from repository records and passed to PyQt6 screens.
- **Data structures:** lists of domain objects drive the community, tank, and alert views; filtering/search updates displayed records.
- **GUI:** all screens and charts are native PyQt6 widgets; no JavaScript, web UI, or React Native runtime is used.
- **Database:** `AssetRepository` defines the storage interface. `DemoRepository` supports offline demonstrations; `PostgresRepository` provides PostgreSQL persistence using psycopg2 and parameterized statements.
- **CRUD:** tank and community screens plus sensor, transaction, equipment, maintenance, and technician lists provide validated add/edit/delete flows backed by the selected repository. Alerts can be marked resolved. Report data can be exported as CSV.
- **DPG-minded design:** readable status labels supplement color, form validation protects data, and the layout keeps operational information clear and accessible.

## Project structure

```text
main.py          PyQt6 interface, domain model, repositories, and application entry point
requirements.txt Runtime dependencies
.env.example     PostgreSQL connection setting example
```

Dashboard charts and activity summaries are currently illustrative. A production IoT deployment would connect the sensor records to a live ingestion service and add authenticated user accounts and audit logging.
