import pytest

from app.services.categoriser import categorise


class TestCategorise:
    def test_ai_security_prompt_injection(self):
        assert categorise("New prompt injection attack discovered", "") == "ai_security"

    def test_ai_security_deepfake(self):
        assert categorise("Deepfake audio used in corporate fraud", "") == "ai_security"

    def test_vulnerabilities_cve(self):
        assert categorise("CVE-2024-12345 affects millions of devices", "") == "vulnerabilities"

    def test_vulnerabilities_zero_day(self):
        assert categorise("Zero-day exploit found in popular browser", "") == "vulnerabilities"

    def test_vulnerabilities_rce(self):
        assert categorise("Critical RCE discovered in web framework", "") == "vulnerabilities"

    def test_malware_ransomware(self):
        assert categorise("New ransomware strain targets hospitals", "") == "malware"

    def test_malware_botnet(self):
        assert categorise("Botnet compromises 500,000 routers", "") == "malware"

    def test_malware_rootkit(self):
        assert categorise("Researchers find rootkit in firmware updates", "") == "malware"

    def test_threat_intel_apt(self):
        assert categorise("APT29 attributed to recent embassy breach", "") == "threat_intel"

    def test_threat_intel_ioc(self):
        assert categorise("New IOC list released for current campaign", "") == "threat_intel"

    def test_appsec_xss(self):
        assert categorise("XSS vulnerability patched in major CMS", "") == "appsec"

    def test_appsec_sql_injection(self):
        assert categorise("SQL injection flaw exposes user database", "") == "appsec"

    def test_appsec_ssrf(self):
        assert categorise("SSRF bug allows internal network access", "") == "appsec"

    def test_cloud_security_aws(self):
        assert categorise("Misconfigured AWS S3 bucket leaks data", "") == "cloud_security"

    def test_cloud_security_kubernetes(self):
        assert categorise("Kubernetes cluster exposed without auth", "") == "cloud_security"

    def test_compliance_gdpr(self):
        assert categorise("Company fined under GDPR for data breach", "") == "compliance"

    def test_compliance_nist(self):
        assert categorise("NIST releases updated cybersecurity framework", "") == "compliance"

    def test_privacy_data_breach(self):
        assert categorise("Data breach exposes 10 million records", "") == "privacy"

    def test_privacy_surveillance(self):
        assert categorise("Government surveillance program revealed", "") == "privacy"

    def test_general_fallback(self):
        assert categorise("Tech company announces earnings report", "") == "general"

    def test_content_fallback_used(self):
        # title has no keywords, but content snippet does
        result = categorise("Breaking news", "ransomware group claims responsibility")
        assert result == "malware"

    def test_priority_ai_security_over_vulnerabilities(self):
        # "prompt injection" should win over "exploit"
        result = categorise("prompt injection exploit found", "")
        assert result == "ai_security"

    def test_case_insensitive(self):
        assert categorise("RANSOMWARE Attack Detected", "") == "malware"

    def test_empty_inputs(self):
        assert categorise("", "") == "general"
