"""Evidence-based project detection and advisory repository checks."""

import hashlib
import json
from pathlib import PurePosixPath
import re

from .config import CHECK_IDS, tomllib


SEVERITIES = {"info": 0, "warning": 1, "error": 2}


def _has_section(content, words):
    # Match Markdown/RST headings and common plain-text documentation labels.
    for line in content.splitlines():
        stripped = line.strip().lower().strip("# :")
        if len(stripped) < 90 and any(re.search(r"\b" + word + r"\b", stripped) for word in words):
            return True
    return False


def analyze(files, contents, large_files, enabled=None):
    enabled = set(CHECK_IDS if enabled is None else enabled)
    names = {name.lower(): name for name in files}
    findings = []
    projects = []
    basics = []

    def finding(check, title, suggestion, path=None, severity="warning", evidence=None):
        if check not in enabled:
            return
        identity = hashlib.sha256(f"{check}\0{path or ''}".encode("utf-8", "surrogatepass")).hexdigest()[:20]
        findings.append({"id": identity, "check": check, "severity": severity,
                         "title": title, "suggestion": suggestion, "path": path,
                         "line": None, "evidence": evidence})

    readme = next((names[n] for n in ("readme.md", "readme.rst", "readme.txt", "readme") if n in names), None)
    rules = [
        ("readme", "README", readme is not None, "Add a root README with installation and usage examples."),
        ("license", "License", any(n in names for n in ("license", "license.md", "license.txt", "copying")), "Choose an appropriate license and add its full text in a root LICENSE file."),
        ("gitignore", "Git ignore rules", ".gitignore" in names, "Add a .gitignore for generated files and local development artifacts."),
        ("contributing", "Contributing guide", any(n in names for n in ("contributing.md", "contributing.rst", ".github/contributing.md")), "Add CONTRIBUTING.md with setup, test commands, and contribution expectations."),
        ("tests", "Tests", any(_test_file(n) for n in files), "Add focused regression tests and document how to run them."),
        ("ci", "GitHub Actions workflow", any(n.startswith(".github/workflows/") and n.endswith((".yml", ".yaml")) for n in names), "Add a GitHub Actions workflow that installs the project and runs tests."),
    ]
    for check, label, passed, suggestion in rules:
        basics.append({"id": check, "label": label, "passed": passed, "enabled": check in enabled})
        if not passed:
            finding(check, f"No {label.lower()} detected", suggestion, severity="info" if check == "contributing" else "warning")
    if readme and readme in contents:
        content = contents[readme]
        if not _has_section(content, ("install", "installation", "setup", "start", "getting started")):
            finding("readme-install", "README has no installation section", "Add prerequisites and exact setup or installation commands under an Installation or Getting Started heading.", readme)
        if not _has_section(content, ("usage", "use", "example", "examples", "run", "reports")):
            finding("readme-usage", "README has no usage section", "Add a runnable example and describe the expected result under a Usage or Examples heading.", readme)

    for path in files:
        name = PurePosixPath(path).name
        kind = {"pyproject.toml": "Python", "requirements.txt": "Python", "setup.py": "Python", "package.json": "Node", "Cargo.toml": "Rust", "go.mod": "Go"}.get(name)
        if not kind:
            continue
        project = {"type": kind, "path": path, "directory": str(PurePosixPath(path).parent), "frameworks": [], "manifest_status": "not-parsed"}
        projects.append(project)
        content = contents.get(path)
        if content is None:
            project["manifest_status"] = "unread"
            continue
        if name in ("requirements.txt", "setup.py"):
            continue
        try:
            if kind == "Node":
                data = json.loads(content)
                if not isinstance(data, dict):
                    raise ValueError("expected a JSON object")
                for key in ("scripts", "dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                    if key in data and (not isinstance(data[key], dict) or any(not isinstance(v, str) for v in data[key].values())):
                        raise ValueError(f"{key} must be an object of strings")
                scripts = data.get("scripts", {})
                deps = set().union(*(data.get(key, {}) for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies")))
                framework_map = {"react": "React", "next": "Next.js", "vue": "Vue", "svelte": "Svelte", "express": "Express", "@angular/core": "Angular", "vite": "Vite"}
                project["frameworks"] = sorted({label for dep, label in framework_map.items() if dep in deps})
                test = scripts.get("test", "").strip()
                if not test or "no test specified" in test.lower():
                    finding("node-test-script", "Node project has no usable test script", 'Add a scripts.test command in package.json that runs the project test suite.', path)
                directory = PurePosixPath(path).parent
                if not any((directory / lock).as_posix() in files for lock in ("package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "bun.lock", "bun.lockb")):
                    finding("node-lockfile", "Node project has no lockfile", "Generate and commit the lockfile for your package manager so dependency resolution is reproducible.", path)
            elif kind in ("Python", "Rust"):
                data = tomllib.loads(content)
                section_name = "project" if kind == "Python" else "package"
                section = data.get(section_name, {})
                if not isinstance(section, dict):
                    raise ValueError(f"{section_name} must be a table")
                if kind == "Python":
                    dependencies = section.get("dependencies", [])
                    if not isinstance(dependencies, list) or any(not isinstance(v, str) for v in dependencies):
                        raise ValueError("project.dependencies must be an array of strings")
                    dep_names = {re.split(r"[\s\[<>=!~;]", v.strip().lower())[0] for v in dependencies}
                    project["frameworks"] = sorted({label for dep, label in {"django": "Django", "flask": "Flask", "fastapi": "FastAPI"}.items() if dep in dep_names})
                    if section and not section.get("requires-python") and "requires-python" not in section.get("dynamic", []):
                        finding("python-version", "Python package has no declared Python version", 'Set project.requires-python in pyproject.toml to the versions you support.', path)
                elif section and not section.get("edition") and not data.get("workspace", {}).get("package", {}).get("edition"):
                    finding("rust-edition", "Rust package has no declared edition", "Declare package.edition or inherit a declared workspace edition in Cargo.toml.", path)
            else:
                module = re.search(r"(?m)^\s*module\s+([^\s]+)", content)
                if module is None:
                    raise ValueError("missing module directive")
                if not re.search(r"(?m)^\s*go\s+\d+\.\d+(?:\.\d+)?\s*(?://.*)?$", content):
                    finding("go-version", "Go module has no declared Go version", "Add a go directive in go.mod declaring the minimum Go toolchain version.", path)
            project["manifest_status"] = "parsed"
        except (ValueError, TypeError, AttributeError) as error:
            project["manifest_status"] = "invalid"
            finding("manifest-valid", "Project manifest could not be parsed", "Correct the manifest syntax or field types, then scan again. RepoPulse never runs the manifest.", path, "error", str(error)[:240])

    for item in large_files:
        finding("large-files", "File exceeds the configured size threshold", "Review whether this belongs in source control; consider generated-file exclusions or Git LFS for large assets.", item["path"], "info", f"{item['bytes']:,} bytes")
    active = [check for check in basics if check["enabled"]]
    score = round(100 * sum(check["passed"] for check in active) / len(active)) if active else None
    findings.sort(key=lambda f: (-SEVERITIES[f["severity"]], f["check"], f["path"] or ""))
    return basics, score, projects, findings


def _test_file(path):
    file = PurePosixPath(path)
    name = file.name.lower()
    suffix = file.suffix.lower()
    if suffix not in (".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".cs", ".rb", ".php", ".cpp", ".c", ".kt", ".swift"):
        return False
    return (
        any(part.lower() in ("test", "tests", "__tests__") for part in file.parts[:-1])
        or name.startswith("test_")
        or name.endswith(("_test.go", ".test.ts", ".test.tsx", ".test.js", ".test.jsx", ".spec.ts", ".spec.tsx", ".spec.js", ".spec.jsx"))
    )
