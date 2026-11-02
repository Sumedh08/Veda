from pathlib import Path

from scripts import scan_secrets


def test_secret_scanner_detects_provider_tokens_without_returning_values(
    capsys, monkeypatch, tmp_path
):
    token = "sk-or-v1-" + ("a5" * 32)
    source = tmp_path / ".env"
    source.write_text(f'OPENROUTER_API_KEY="{token}"\n', encoding="utf-8")
    monkeypatch.setattr(scan_secrets, "ROOT", tmp_path)

    assert scan_secrets.main() == 1
    output = capsys.readouterr().out
    assert "possible openai_or_openrouter_key" in output
    assert token not in output


def test_secret_scanner_detects_generic_literal_and_private_key_header():
    opaque = "CredentialValue" + ("8Q" * 16)
    findings = scan_secrets.scan_text(
        f'LOCAL_PROVIDER_SECRET="{opaque}"\n-----BEGIN ' + "PRIVATE KEY-----"
    )
    assert [(item.rule, item.line) for item in findings] == [
        ("secret_assignment", 1),
        ("private_key_header", 2),
    ]


def test_secret_scanner_detects_provider_prefixed_api_key_setting_without_value():
    value = "nonreal-sensitive-value-1234567890"
    findings = scan_secrets.scan_text(f'SARVAM_API_KEY="{value}"')

    assert [(item.rule, item.line) for item in findings] == [("secret_assignment", 1)]


def test_secret_scanner_cli_reports_prefixed_key_without_exposing_value(
    capsys, monkeypatch, tmp_path
):
    value = "nonreal-sensitive-value-1234567890"
    (tmp_path / ".env").write_text(f'SARVAM_API_KEY="{value}"\n', encoding="utf-8")
    monkeypatch.setattr(scan_secrets, "ROOT", tmp_path)

    assert scan_secrets.main() == 1
    output = capsys.readouterr().out
    assert ".env:1: possible secret_assignment" in output
    assert value not in output


def test_secret_scanner_ignores_documented_placeholders_safe_local_urls_and_reasoned_line_exceptions():
    findings = scan_secrets.scan_text(
        'DEV_AUTH_SECRET="replace-with-a-long-random-local-only-secret"\n'
        'API_TEST_SECRET="test-only-not-a-real-local-restart-secret"\n'
        'DATABASE_URL="postgresql+psycopg://veda:fixture-password@localhost/veda"\n'
        'KNOWN_PUBLIC_TEST_VECTOR="'
        + ("z8" * 16)
        + '" # veda-secret-scan:ignore -- published non-credential fixture\n'
    )
    assert findings == []


def test_secret_scanner_reports_uninspected_oversized_source_file(capsys, monkeypatch, tmp_path):
    source = tmp_path / "large.md"
    source.write_bytes(b"x" * (scan_secrets.MAX_FILE_BYTES + 1))
    monkeypatch.setattr(scan_secrets, "ROOT", tmp_path)

    assert scan_secrets.main() == 2
    assert "could not inspect 1 text file" in capsys.readouterr().out


def test_secret_scanner_skips_generated_and_binary_trees(tmp_path):
    generated = tmp_path / "node_modules"
    generated.mkdir()
    (generated / "bundle.js").write_text("x", encoding="utf-8")
    (tmp_path / "image.png").write_bytes(b"x")
    oversized: list[Path] = []
    assert list(scan_secrets.iter_source_files(tmp_path, oversized)) == []
    assert oversized == []
