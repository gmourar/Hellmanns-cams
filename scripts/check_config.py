"""Valida .env do agent e backend (sem imprimir segredos)."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]


def load_env(path: Path) -> dict:
    data = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip()
    return data


def check_pair(name: str, agent: dict, backend: dict, keys: list[str]) -> list[str]:
    issues = []
    for key in keys:
        av = agent.get(key, "")
        bv = backend.get(key, "")
        aliases = {
            "S3_BUCKET": ("S3_BUCKET", "AWS_BUCKET_NAME"),
            "S3_PUBLIC_URL": ("S3_PUBLIC_URL", "AWS_BUCKET_URL"),
        }
        if key in aliases:
            for alias in aliases[key]:
                av = av or agent.get(alias, "")
                bv = bv or backend.get(alias, "")
        if av != bv and av and bv:
            issues.append(f"{name}: '{key}' diferente entre agent e backend")
    return issues


def main():
    agent = load_env(ROOT / "agent" / ".env")
    backend = load_env(ROOT / "backend" / ".env")
    issues: list[str] = []
    ok: list[str] = []

    bucket = agent.get("S3_BUCKET") or agent.get("AWS_BUCKET_NAME") or backend.get("AWS_BUCKET_NAME")
    public = agent.get("S3_PUBLIC_URL") or agent.get("AWS_BUCKET_URL") or backend.get("AWS_BUCKET_URL")
    token_a = agent.get("AGENT_TOKEN", "")
    token_b = backend.get("AGENT_TOKEN", "")
    has_creds = any(
        agent.get(k) or backend.get(k)
        for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")
    )

    if bucket:
        ok.append(f"Bucket S3: {bucket}")
    else:
        issues.append("Bucket S3 não definido (AWS_BUCKET_NAME ou S3_BUCKET)")

    if public:
        ok.append(f"URL pública: {public}")
    else:
        issues.append("URL pública ausente (AWS_BUCKET_URL ou S3_PUBLIC_URL)")

    if token_a and token_a == token_b:
        ok.append("AGENT_TOKEN igual em agent e backend")
    else:
        issues.append("AGENT_TOKEN ausente ou diferente entre agent e backend")

    if has_creds:
        ok.append("Credenciais AWS (ACCESS_KEY) presentes no .env")
    else:
        ok.append("Credenciais AWS: usando perfil padrão (AWS CLI / IAM) — OK se já configurado na máquina")

    serial = agent.get("SERIAL_TO_CABINE", "")
    cabs = []
    for part in serial.split(","):
        if ":" in part:
            cabs.append(part.rsplit(":", 1)[1].strip())
    if len(cabs) != len(set(cabs)):
        issues.append("SERIAL_TO_CABINE: duas câmeras com o mesmo número de cabine")

    issues.extend(check_pair("região", agent, backend, ["AWS_REGION"]))
    issues.extend(check_pair("bucket", agent, backend, ["S3_BUCKET"]))

    upload = agent.get("UPLOAD_TO_S3", "").lower()
    if bucket and upload in ("0", "false", "no"):
        issues.append("UPLOAD_TO_S3=false mas bucket configurado — upload desligado")
    elif bucket:
        ok.append("Upload S3: ativo (bucket configurado)")

    storage = backend.get("STORAGE_BACKEND", "").lower()
    if storage == "local" and bucket:
        issues.append("STORAGE_BACKEND=local conflita com bucket — remova ou use STORAGE_BACKEND=s3")
    elif bucket:
        ok.append("Backend galeria: modo S3 (auto ou explícito)")

    print("=== Config Hellmanns Cam ===\n")
    for line in ok:
        print(f"  OK  {line}")
    for line in issues:
        print(f"  !!  {line}")

    if issues:
        print("\nCorrija os itens acima e reinicie agent + backend.")
        sys.exit(1)
    print("\nConfiguração consistente.")
    sys.exit(0)


if __name__ == "__main__":
    main()
