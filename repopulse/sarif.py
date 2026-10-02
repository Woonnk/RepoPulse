"""Export advisory findings in the SARIF 2.1.0 interchange format."""

from urllib.parse import quote

from . import __version__


def render_sarif(report):
    checks = sorted({finding["check"] for finding in report["findings"]})
    indices = {check: index for index, check in enumerate(checks)}
    new_ids = {f["id"] for f in report.get("comparison", {}).get("new_findings", [])}
    warnings = list(dict.fromkeys(report["warnings"] + report.get("comparison", {}).get("warnings", [])))
    results = []
    for finding in report["findings"]:
        message = finding["title"]
        if finding["evidence"]:
            message += "\nEvidence: " + finding["evidence"]
        message += "\nSuggestion: " + finding["suggestion"]
        result = {
            "ruleId": finding["check"], "ruleIndex": indices[finding["check"]],
            "level": {"info": "note", "warning": "warning", "error": "error"}[finding["severity"]],
            "message": {"text": message},
            "partialFingerprints": {"repopulse/v1": finding["id"]},
        }
        if finding["path"]:
            physical = {"artifactLocation": {"uri": quote(finding["path"], safe="/")}}
            if type(finding.get("line")) is int and finding["line"] > 0:
                physical["region"] = {"startLine": finding["line"]}
            result["locations"] = [{"physicalLocation": physical}]
        if "comparison" in report:
            # Unknown coverage must not be represented as an unchanged result.
            unread = report["comparison"]["uncompared_content_files"]
            if finding["path"] not in unread:
                result["baselineState"] = "new" if finding["id"] in new_ids else "unchanged"
        results.append(result)
    run = {
        "tool": {"driver": {
            "name": "RepoPulse", "version": __version__,
            "informationUri": "https://github.com/Woonnk/RepoPulse",
            "rules": [{"id": check, "shortDescription": {"text": check.replace("-", " ")}} for check in checks],
        }},
        "results": results,
        "invocations": [{"executionSuccessful": True, "toolExecutionNotifications": [
            {"level": "warning", "message": {"text": warning}} for warning in warnings
        ]}],
    }
    return {"$schema": "https://json.schemastore.org/sarif-2.1.0.json", "version": "2.1.0", "runs": [run]}
