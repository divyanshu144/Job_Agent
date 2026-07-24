#!/usr/bin/env python3
"""Exits 1 if field names in backend/schemas.py diverge from frontend/src/types/index.ts."""
import re
import sys
from pathlib import Path

PY = Path("backend/schemas.py").read_text()
TS = Path("frontend/src/types/index.ts").read_text()

PAIRS = [
    ("JobParserOutput", "JobParserOutput"),
    ("MatchScorerOutput", "MatchScorerOutput"),
    ("GapAnalystOutput", "GapAnalystOutput"),
    ("ResourcePlannerOutput", "ResourcePlannerOutput"),
    ("CoverLetterOutput", "CoverLetterOutput"),
    ("ResumeTailorerOutput", "ResumeTailorerOutput"),
    ("GapItem", "GapItem"),
    ("ResourceItem", "ResourceItem"),
    ("BulletItem", "BulletItem"),
    ("CampaignRunResponse", "CampaignRun"),
    ("TargetCompanyResponse", "TargetCompany"),
    ("ResumeDocumentResponse", "ResumeDocumentResponse"),
    ("ResumeVersionSummary", "ResumeVersionSummary"),
    ("ResumeRevisionSummary", "ResumeRevisionSummary"),
    ("ResumeChatResult", "ResumeChatResult"),
    ("EditRuleResponse", "EditRuleResponse"),
    ("ResumeIdentity", "ResumeIdentity"),
]


def py_fields(name: str) -> set:
    m = re.search(rf"class {name}\(BaseModel\):(.*?)(?=\nclass |\Z)", PY, re.DOTALL)
    if not m:
        return set()
    return set(re.findall(r"^\s{4}(\w+)\s*:", m.group(1), re.MULTILINE)) - {
        "model_config"
    }


def ts_fields(name: str) -> set:
    m = re.search(rf"interface {name}\s*\{{(.*?)\}}", TS, re.DOTALL)
    return set(re.findall(r"(\w+)\??:", m.group(1))) if m else set()


errors = []
for py_name, ts_name in PAIRS:
    pf, tf = py_fields(py_name), ts_fields(ts_name)
    if not pf:
        errors.append(f"Python class {py_name} not found")
        continue
    if not tf:
        errors.append(f"TS interface {ts_name} not found")
        continue
    if pf - tf:
        errors.append(f"{py_name}: Python-only fields: {pf - tf}")
    if tf - pf:
        errors.append(f"{ts_name}: TS-only fields: {tf - pf}")

if errors:
    print("Schema drift detected:")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)

print(f"Schema drift check passed ({len(PAIRS)} classes)")
