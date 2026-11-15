import io
import json
from pathlib import Path
import runpy
import subprocess
import sys
from types import SimpleNamespace


def test_canary_preserves_signing_identity_without_secret_arguments(monkeypatch, tmp_path, capsys):
    ca = tmp_path / "public-ca.pem"
    ca.write_text("public certificate fixture")
    monkeypatch.setattr(sys, "argv", ["stage_sponsors.py", "--image", "valio:test", "--commit", "a" * 40,
                                   "--name", "valio-test-canary", "--ca", str(ca), "--url", "https://valio-sponsor.72.61.22.106.sslip.io"])
    provider = {"AIVEN_DATABASE_URL": "postgresql://test.invalid/db", "CLOUDINARY_CLOUD_NAME": "cloud-test",
                "CLOUDINARY_API_KEY": "cld-test-value", "CLOUDINARY_API_SECRET": "cld-private-test-value",
                "ELEVENLABS_API_KEY": "speech-test-value"}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(provider)))
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if command[:2] == ["docker", "inspect"]:
            return SimpleNamespace(returncode=0, stdout=json.dumps([{"Config": {"Env": [
                "VALIO_API_KEY=supplier-test-value", "GEMINI_API_KEY=gemini-test-value",
                "KITCHEN_SIGNING_KEY=signing-test-value", "CHEF_MODEL=existing-model"]}}]))
        # Remove the environment before any assertion can cause pytest to repr it.
        execution = kwargs.pop("env")
        signing = execution.get("KITCHEN_SIGNING_KEY")
        model = execution.get("CHEF_MODEL")
        cloud = execution.get("CLOUDINARY_API_SECRET")
        leaked_executor = any(key.startswith("BROWSER_USE") for key in execution)
        execution.clear()
        assert signing == "signing-test-value"
        assert model == "existing-model"
        assert cloud == "cld-private-test-value"
        assert not leaked_executor
        assert "127.0.0.1:8078:8000" in command
        assert all("test-value" not in arg for arg in command)
        assert "--volumes-from" in command and "valio:ro" in command
        assert "traefik.http.routers.valio-test-canary.rule=Host(`valio-sponsor.72.61.22.106.sslip.io`)" in command
        assert not any(arg.startswith("traefik.http.routers.valio.") for arg in command)
        return SimpleNamespace(returncode=0, stdout="container-id")
    monkeypatch.setattr(subprocess, "run", run)
    runpy.run_path(str(Path(__file__).parents[1] / "scripts/stage_sponsors.py"), run_name="__main__")
    output = capsys.readouterr().out
    assert "test-value" not in output
    assert json.loads(output)["production_untouched"] is True
    assert len(calls) == 2
