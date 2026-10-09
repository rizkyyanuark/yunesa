from pathlib import Path
import argparse
import secrets

def main():
    parser = argparse.ArgumentParser(description="Create local .env with generated secrets.")
    parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    destination = root / ".env"
    if destination.exists():
        raise SystemExit(".env already exists; no file was overwritten.")
    text = (root / ".env.example").read_text(encoding="utf-8")
    values = {
        "GLOBAL_PASSWORD": secrets.token_urlsafe(24),
        "JWT_SECRET_KEY": secrets.token_hex(32),
        "AIRFLOW_SECRET_KEY": secrets.token_hex(32),
        "AIRFLOW_JWT_SECRET": secrets.token_hex(32),
        "HOST_DATA_DIR": (root / "data").as_posix(),
        "HOST_PACKAGE_DIR": (root / "backend/package").as_posix(),
    }
    values["POSTGRES_PASSWORD"] = values["GLOBAL_PASSWORD"]
    values["NEO4J_PASSWORD"] = values["GLOBAL_PASSWORD"]
    lines = []
    for line in text.splitlines():
        key, separator, _ = line.partition("=")
        if separator and key in values:
            line = key + "=" + values[key]
        lines.append(line)
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(lines) + "\n")
    destination.chmod(0o600)
    print("Created .env. Fill external provider credentials locally.")

if __name__ == "__main__":
    main()
