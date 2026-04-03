import json
import os
import platform
from pathlib import Path

APP_NAME = "PulseMeter"


def _config_dir() -> Path:
    """Return the platform-appropriate user config directory for this app.

    Windows : %APPDATA%\\PulseMeter
    macOS   : ~/Library/Application Support/PulseMeter
    Linux   : $XDG_CONFIG_HOME/PulseMeter  (default: ~/.config/PulseMeter)
    """
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))

    return base / APP_NAME


class SetItem():
    def __init__(self, name:str) -> None:
        self.setting_name = name

class SystemSetting(SetItem):
    def __init__(self) -> None:
        super().__init__("systemsetting")
        self.interval = 0.6
        self.meter1 = "cpu"
        self.meter2 = "cpu"
        self.net_dev = "eth0"
        self.server_ip = ""


class Setting():
    def __init__(self) -> None:
        self.systemsetting = SystemSetting()

        config_dir = _config_dir()
        config_dir.mkdir(parents=True, exist_ok=True)
        self.save_filename = config_dir / "sys-settings.json"

        if self.save_filename.is_file():
            self.load(self.save_filename)
        else:
            print(f"Can't find settings file, save a default settings to {self.save_filename}")
            self.save(self.save_filename)


    def save(self, path: str) -> bool:
        if isinstance(path, Path):
            path = str(path)
        ss = {k: v for k, v in self.systemsetting.__dict__.items() if k != "server_ip"}
        mate = {"systemsetting": ss}
        jsonString = json.dumps(mate, indent=2, ensure_ascii=True)
        with open(path, "w") as f:
            f.write(jsonString)
            print('parameters saved')
            return True
        return False

    def load(self, path: str) -> bool:
        if isinstance(path, Path):
            path = str(path)
        try:
            with open(path, "r") as f:
                js:dict = json.loads(f.read())
        except FileNotFoundError:
            print(f'File "{path}" not found')
            return False

        for k, v in js["systemsetting"].items():
            if k != "server_ip":
                setattr(self.systemsetting, k, v)

        return True

if __name__ == "__main__":
    s = Setting()
    print(f"Config path: {s.save_filename}")
    print(s.systemsetting.__dict__)
