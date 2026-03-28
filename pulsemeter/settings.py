import json
from pathlib import Path


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
        
        self.save_filename = Path("./sys-settings.json")
        if self.save_filename.is_file():
            self.load(self.save_filename)
        else:
            # save a default settings
            print("Can't find settings file, save a default settings")
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
    print(s.systemsetting.__dict__)
