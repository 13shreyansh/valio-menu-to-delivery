"""Stage a private canary on the VPS. Secrets arrive through encrypted stdin.

Run via SSH with a JSON object on stdin containing only new provider env vars.
The existing valio container's environment is captured in memory and reused.
No key file, Docker env file or secret-bearing command argument is created.
This script does not modify the production container, proxy or database.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

KEYS = {
    "AIVEN_DATABASE_URL", "CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET",
    "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID", "ELEVENLABS_STT_MODEL", "ELEVENLABS_TTS_MODEL",
}
BASE_KEYS = {"VALIO_API_KEY", "VALIO_API_BASE", "GEMINI_API_KEY", "CHEF_MODEL", "KITCHEN_SIGNING_KEY", "PUBLIC_URL"}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--port", type=int, default=8078)
    parser.add_argument("--ca", type=Path, required=True)
    parser.add_argument("--url", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]+", args.name) or not re.fullmatch(r"[a-f0-9]{40}", args.commit):
        raise SystemExit("Use an explicit canary name and full commit hash.")
    address = urlsplit(args.url)
    if (not args.ca.is_file() or address.scheme != "https" or not address.hostname or
        not address.hostname.endswith(".72.61.22.106.sslip.io") or address.port or address.username or
        address.path not in ("", "/") or address.query or address.fragment or not 1024 < args.port < 65536):
        raise SystemExit("Use a public CA file, an HTTPS canary URL and a valid private port.")
    provider = json.load(sys.stdin)
    if not isinstance(provider, dict) or set(provider) - KEYS or not all(isinstance(v, str) for v in provider.values()):
        raise SystemExit("Unexpected provider configuration.")
    required = {"AIVEN_DATABASE_URL", "CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET", "ELEVENLABS_API_KEY"}
    if not all(provider.get(key) for key in required):
        raise SystemExit("All provider credentials are required for this canary.")
    old = subprocess.run(["docker", "inspect", "valio"], check=True, capture_output=True, text=True)
    source = json.loads(old.stdout)[0]
    existing = dict(item.split("=", 1) for item in source["Config"]["Env"] if "=" in item)
    env = {key: value for key, value in existing.items() if key in BASE_KEYS}
    if not env.get("VALIO_API_KEY") or not env.get("GEMINI_API_KEY"):
        raise SystemExit("The existing runtime's supplier and model credentials are required.")
    env.update(provider)
    env.update(AIVEN_CA_CERT_PATH="/run/valio/aiven-ca.pem", BUILD_COMMIT=args.commit,
               PUBLIC_URL=args.url, AURORA_LOCAL_DB="/data/accounts.sqlite")
    # Mount the old documents read-only for migration inspection. Aiven is mandatory above.
    command = ["docker", "run", "-d", "--name", args.name, "--restart", "unless-stopped",
               "-p", f"127.0.0.1:{args.port}:8000", "--volumes-from", "valio:ro",
               "--mount", f"type=bind,src={args.ca.resolve()},dst=/run/valio/aiven-ca.pem,readonly"]
    # Docker discovery routes only this new container. No shared proxy restart or production label change.
    labels = source["Config"].get("Labels") or {}
    entrypoint = labels.get("traefik.http.routers.valio.entrypoints", "websecure")
    resolver = labels.get("traefik.http.routers.valio.tls.certresolver", "letsencrypt")
    command += ["--label", "traefik.enable=true",
                "--label", f"traefik.http.routers.{args.name}.rule=Host(`{address.hostname}`)",
                "--label", f"traefik.http.routers.{args.name}.entrypoints={entrypoint}",
                "--label", f"traefik.http.routers.{args.name}.tls.certresolver={resolver}",
                "--label", f"traefik.http.services.{args.name}.loadbalancer.server.port=8000"]
    for key in env:
        command += ["--env", key]
    command.append(args.image)
    execution = {key: os.environ[key] for key in ("PATH", "HOME", "DOCKER_HOST", "DOCKER_CONTEXT", "XDG_RUNTIME_DIR") if key in os.environ}
    run = subprocess.run(command, env={**execution, **env}, capture_output=True, text=True)
    if run.returncode:
        raise SystemExit("Canary creation failed. Inspect Docker status without printing environment values.")
    print(json.dumps({"name": args.name, "private_port": args.port, "commit": args.commit,
                      "providers_configured": sorted(required), "production_untouched": True}))
