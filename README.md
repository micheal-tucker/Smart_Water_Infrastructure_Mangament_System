# SWIMS

**Smart Water Infrastructure Management System** is a Python desktop application for monitoring community water infrastructure. Utility operators can manage water tanks, communities, sensors, valves, transactions, equipment, alerts, and maintenance records from a PyQt6 interface.

SWIMS is a final-year object-oriented programming project. It uses PostgreSQL for persistent data and includes an in-memory demo mode for exploring the interface without a database.

## Features

- Dashboard with community, tank, water-level, and alert summaries
- Community and tank management with add, edit, delete, search, and filtering
- Sensor, transaction, equipment, valve, maintenance, and technician record management
- Alert messages with severity and resolve actions
- PDF and Excel reports for usage, tank status, alerts, and maintenance
- Light and dark appearance options
- PostgreSQL persistence and sample-data demo mode

## Requirements

- Python 3.10 or newer
- PostgreSQL for persistent storage; optional for demo mode
- Windows, macOS, or Linux with a graphical desktop environment

## Quick start

From the project directory, install the Python dependencies and start SWIMS:

```bash
python -m pip install -r requirements.txt
python main.py
```

On Windows, the Python launcher also works:

```powershell
py -m pip install -r requirements.txt
py main.py
```

If no database settings are found, the app starts with **DEMO DATA**. Changes in demo mode are kept in memory and are lost when the application closes.

## PostgreSQL configuration

1. Create a PostgreSQL database, such as `swims`.
2. Copy `.env.example` to `.env` in the project directory.
3. Set `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD` in `.env`.
4. Start the app with `python main.py` or `py main.py`.

SWIMS reads `.env` automatically. Environment variables already set in the shell take precedence. Alternatively, configure `SWIMS_DATABASE_URL` with a PostgreSQL connection URL.

`.env` is excluded from Git. Do not commit database passwords, connection URLs containing passwords, or production credentials.

SWIMS connects to the existing tables `communities`, `water_tanks`, `sensors`, `sensor_readings`, `valves`, `water_transactions`, `equipment`, `maintenance`, `technicians`, and `alerts`. At startup it checks that the expected schema is present. If the `maintenance.status` column is missing, the app adds it for the assignment's maintenance workflow.

## Sign-in

For the assignment demonstration, sign in using one of these usernames. The password is the username followed by `123`:

| Username | Password |
| --- | --- |
| Donald | `Donald123` |
| Michael | `Michael123` |
| Aziz | `Aziz123` |
| Joshua | `Joshua123` |
| Mohamed | `Mohamed123` |
| Alex | `Alex123` |

Usernames are case-insensitive. These credentials are hard-coded for demonstration and are **not suitable for production**. Anyone with access to the public source can see them. Do not use this sign-in flow to protect a deployed service or sensitive database.

## Reports

The Reports screen exports water usage, tank status, alerts, and maintenance records in PDF and Excel formats. Install the project dependencies from `requirements.txt` to enable both export formats.

## Project structure

```text
main.py          Domain classes, repository implementations, PyQt6 screens, and app entry point
requirements.txt Python dependencies
.env.example     Example PostgreSQL settings (without credentials)
README.md        Setup, operation, and contribution notes
LICENSE          MIT license for this project
```

## Object-oriented programming brief

- `WaterAsset` is an abstract base class. `WaterTank`, `Sensor`, and `Equipment` specialize it and override `summary()`.
- `WaterTank` controls access to capacity, level, and status through properties.
- `Community` and `Alert` are data classes used by the interface and repositories.
- `AssetRepository` defines the persistence interface. `DemoRepository` provides sample data and `PostgresRepository` stores records in PostgreSQL.
- Lists of domain objects support the community, tank, and alert views; forms and tables provide record management.
- The interface uses native PyQt6 widgets and the application logic is written in Python.

## Current scope

Sensor readings are managed as application records. SWIMS does not currently receive live messages from an ESP32 or other IoT device. Dashboard usage charts are illustrative. Production use would need secure user authentication, authorization, audit logging, and a live sensor-ingestion service.

## Contributing

Friends and collaborators can work on a branch and open a pull request for review:

1. Create a feature branch from the latest `main` branch.
2. Make a focused change and describe how you verified it.
3. Open a pull request and discuss it with the project owner before merging.

To grant repository access, the owner can add collaborators from the repository's **Settings > Collaborators** page on GitHub after publishing the project. Never include `.env` or private database information in a pull request.

## License

This project's source code is released under the MIT License. See [LICENSE](LICENSE). Third-party packages retain their own licenses.
