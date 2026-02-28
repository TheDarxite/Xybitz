_CATEGORIES: list[tuple[str, list[str]]] = [
    (
        "ai_security",
        [
            "shadow ai", "llm attack", "ai security", "model poisoning",
            "prompt injection", "ai agent", "saas ai", "copilot security",
            "generative ai", "deepfake", "ai-generated malware",
        ],
    ),
    (
        "vulnerabilities",
        [
            "cve-", "nvd", "patch tuesday", "zero-day", "zero day",
            "exploit", "vulnerability", "advisory", "cvss", "rce", "remote code",
        ],
    ),
    (
        "malware",
        [
            "ransomware", "trojan", "botnet", "spyware", "wiper",
            "rat ", "dropper", "malware", "backdoor", "stealer", "rootkit",
        ],
    ),
    (
        "threat_intel",
        [
            "apt", "threat actor", "campaign", "nation-state", "ioc",
            "ttps", "mitre att&ck", "threat intelligence", "threat group",
        ],
    ),
    (
        "appsec",
        [
            "xss", "sql injection", "owasp", "api security", "web app",
            "sast", "dast", "burp", "penetration test", "csrf", "ssrf",
        ],
    ),
    (
        "cloud_security",
        [
            "aws", "azure", "gcp", "cloud", "s3 bucket", "iam",
            "kubernetes", "container", "docker", "terraform", "misconfiguration",
        ],
    ),
    (
        "compliance",
        [
            "gdpr", "hipaa", "pci dss", "iso 27001", "nist",
            "regulation", "audit", "compliance", "sox", "dora",
        ],
    ),
    (
        "privacy",
        [
            "data breach", "privacy", "tracking", "surveillance",
            "personal data", "leak", "deanonymization", "biometric",
        ],
    ),
]


def categorise(title: str, content: str) -> str:
    """Return the best-matching category slug, or 'general' if no match."""
    text = (title + " " + content[:500]).lower()
    for slug, keywords in _CATEGORIES:
        for keyword in keywords:
            if keyword in text:
                return slug
    return "general"
