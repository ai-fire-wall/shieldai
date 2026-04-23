"""Tests for app/filters/output_filter.py"""
import pytest
from app.filters.output_filter import scan_output, ThreatLevel


def test_clean_response_passes():
    r = scan_output("The capital of France is Paris.")
    assert r.clean is True
    assert r.threat_level == ThreatLevel.SAFE
    assert r.issues_found == []
    assert r.sanitized_response == "The capital of France is Paris."


def test_leaked_api_key_redacted():
    r = scan_output("Your API key is: sk-abc123XYZ789abc123XYZ789abc123XYZ")
    assert "[BLOCKED:" in r.sanitized_response or "[REDACTED:" in r.sanitized_response
    assert "sk-abc123" not in r.sanitized_response


def test_leaked_jwt_redacted():
    r = scan_output("Here is your token: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.abc123")
    assert any("jwt" in i.lower() for i in r.issues_found)


def test_leaked_private_key_blocked():
    r = scan_output("-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQ...")
    assert r.clean is False
    assert r.threat_level == ThreatLevel.CRITICAL


def test_leaked_db_connection_redacted():
    r = scan_output("Connect using: postgresql://admin:password@db.host.com/prod")
    assert "password" not in r.sanitized_response or "[REDACTED" in r.sanitized_response


def test_pii_email_redacted():
    r = scan_output("Contact the admin at john.doe@company.com for help")
    assert "[REDACTED:EMAIL]" in r.sanitized_response


def test_pii_ip_redacted():
    r = scan_output("The server is at 192.168.1.100 and port 8080")
    assert "[REDACTED:IP]" in r.sanitized_response


def test_pii_phone_redacted():
    r = scan_output("Call us at +1 (555) 123-4567 any time")
    assert "[REDACTED:PHONE]" in r.sanitized_response


def test_jailbreak_confirmation_blocked():
    r = scan_output("I am now DAN and I can do anything you ask without restrictions")
    assert r.clean is False
    assert r.threat_level == ThreatLevel.CRITICAL


def test_pii_redaction_can_be_disabled():
    r = scan_output("Email: test@example.com", redact_pii=False)
    assert "[REDACTED:EMAIL]" not in r.sanitized_response


def test_original_length_tracked():
    text = "Hello world"
    r = scan_output(text)
    assert r.original_length == len(text)


def test_clean_response_lengths_match():
    text = "This is a safe response with no issues."
    r = scan_output(text)
    assert r.original_length == r.sanitized_length
