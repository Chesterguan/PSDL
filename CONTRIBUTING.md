# Contributing to PSDL

Thank you for your interest in contributing to PSDL (Patient Scenario Definition Language)! This document provides guidelines for contributing.

## Ways to Contribute

| Type | Description | Where |
|------|-------------|-------|
| **Specification** | Propose language features, operators, semantics | `rfcs/` |
| **Implementation** | Build runtimes, backends, tooling | `runtime/` |
| **Documentation** | Improve guides, tutorials, examples | `docs/` |
| **Testing** | Add conformance tests, find edge cases | `tests/` |
| **Examples** | Share clinical scenario definitions | `examples/` |

## Getting Started

### 1. Set Up Development Environment

```bash
# Clone the repository
git clone https://github.com/psdl-lang/psdl.git
cd psdl

# Set up Python environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run tests to verify setup
pytest tests/ -v
```

### 2. Make Your Changes

1. Create a feature branch: `git checkout -b feature/your-feature-name`
2. Make your changes
3. Add tests for new functionality
4. Run tests: `pytest tests/ -v`
5. Update documentation if needed

### 3. Submit a Pull Request

1. Push your branch: `git push origin feature/your-feature-name`
2. Open a Pull Request on GitHub
3. Fill out the PR template
4. Wait for review

## Code Style

### Python
- Follow PEP 8
- Use type hints where appropriate
- Document functions with docstrings
- Keep functions focused and small

### YAML Scenarios
- Use consistent indentation (2 spaces)
- Include comments explaining clinical rationale
- Provide descriptions for all logic rules

## Proposing Language Changes

For significant language changes, please:

1. Open a Discussion first to gather feedback
2. Write an RFC in `rfcs/` using the template
3. Allow time for community review (minimum 2 weeks)
4. Revise based on feedback
5. Submit for final approval

## RFC Template

```markdown
# RFC: [Title]

## Summary
Brief description of the proposal.

## Motivation
Why is this change needed?

## Detailed Design
Technical specification of the change.

## Drawbacks
What are the downsides?

## Alternatives
What other approaches were considered?

## Open Questions
What remains to be decided?
```

## Reporting Issues

When reporting bugs:

1. Check if the issue already exists
2. Include a minimal reproducible example
3. Specify your environment (Python version, OS, etc.)
4. Describe expected vs actual behavior

## Code of Conduct

All contributors must adhere to our [Code of Conduct](CODE_OF_CONDUCT.md). We are committed to providing a welcoming and inclusive environment.

## Questions?

- Open a GitHub Discussion for questions
- Join our community channels (coming soon)

Thank you for helping make PSDL better!
