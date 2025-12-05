# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

We take security seriously in PSDL, especially given its application in healthcare environments.

### How to Report

If you discover a security vulnerability, please report it by:

1. **DO NOT** open a public GitHub issue
2. Email security concerns to: [security@psdl-lang.org] (replace with actual email)
3. Include as much detail as possible:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

### What to Expect

- **Acknowledgment**: We will acknowledge receipt within 48 hours
- **Assessment**: We will assess the vulnerability within 7 days
- **Resolution**: Critical vulnerabilities will be addressed within 30 days
- **Disclosure**: We follow responsible disclosure practices

### Scope

Security concerns relevant to PSDL include:

- Vulnerabilities in the parser that could allow code injection
- Logic flaws that could cause incorrect clinical evaluations
- Issues that could compromise patient data confidentiality
- Denial of service vulnerabilities in the evaluator

### Out of Scope

- Security issues in dependencies (report to those projects)
- Issues requiring physical access to systems
- Social engineering attacks

## Security Best Practices for PSDL Users

When deploying PSDL in clinical environments:

1. **Validate all scenarios** before production use
2. **Use version control** for all scenario definitions
3. **Implement access controls** for scenario editing
4. **Audit all changes** to clinical scenarios
5. **Test thoroughly** with representative data before deployment
6. **Follow your institution's** security and compliance policies

## Healthcare Compliance

PSDL is designed to support compliance with:

- HIPAA (US)
- GDPR (EU)
- FDA Software as Medical Device (SaMD) guidelines
- EU Medical Device Regulation (MDR)

However, **compliance is the responsibility of the implementing organization**. PSDL provides tools for auditability and traceability, but proper implementation and operational procedures are required.
