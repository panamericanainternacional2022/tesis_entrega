import os


def load_dotenv(env_path: str | None = None) -> None:
    if env_path is None:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env_path = os.path.join(base, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("'\"")
            os.environ.setdefault(key, val)
