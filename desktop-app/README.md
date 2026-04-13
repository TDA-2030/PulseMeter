# PulseMeter Desktop App

Python desktop UI for the PulseMeter hardware meter.

## Development

```bash
cd desktop-app
python -m venv .venv
.venv\Scripts\activate
pip install -e .
python -m pulsemeter_desktop
```

The app stores user settings in the platform config directory instead of the repository.

## Packaging

```bash
cd desktop-app
python scripts/build.py
python scripts/build.py --onedir
```
