# garuda/perception/salesforce.py — Salesforce-specific knowledge for perception
#
# Three jobs: decide what kind of file something is (classify), turn huge metadata XML
# into a few lines of facts (summarize_*), and find which Apex classes a file depends on
# (Apex has no import statements, so "imports" are class references in the code).
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from .diff import FileChange
from .items import Priority


# ---------------------------------------------------------------- classify
@dataclass(frozen=True)
class FileKind:
    kind: str
    priority: Priority    # where the file's *content* goes
    strategy: str         # "full" | "flow-summary" | "perm-summary" | "handle"


def classify(path: str) -> FileKind:
    p = path.lower()
    if p.endswith("test.cls"):
        return FileKind("apex-test", Priority.IMPORTANT, "full")
    if p.endswith((".cls", ".trigger")):
        return FileKind("apex", Priority.IMPORTANT, "full")
    if "/lwc/" in p and p.endswith((".js", ".html")):
        return FileKind("lwc", Priority.IMPORTANT, "full")
    if p.endswith(".flow-meta.xml"):
        return FileKind("flow", Priority.SUPPORTING, "flow-summary")
    if p.endswith((".profile-meta.xml", ".permissionset-meta.xml")):
        return FileKind("permissions", Priority.SUPPORTING, "perm-summary")
    if p.endswith((".field-meta.xml", ".object-meta.xml")):
        return FileKind("schema", Priority.SUPPORTING, "full")
    if p.endswith((".layout-meta.xml", ".translation-meta.xml", ".labels-meta.xml",
                   ".listview-meta.xml", "-meta.xml")):
        return FileKind("metadata", Priority.DEFERRABLE, "handle")
    return FileKind("other", Priority.SUPPORTING, "full")


def is_code(path: str) -> bool:
    return classify(path).priority == Priority.IMPORTANT


# ---------------------------------------------------------------- XML helpers
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _kids(el, name):
    return [c for c in el if _local(c.tag) == name]


def _text(el, name, default=""):
    for c in el:
        if _local(c.tag) == name:
            return (c.text or "").strip()
    return default


def _value(el) -> str:
    v = next(iter(_kids(el, "value")), None)
    if v is None:
        return _text(el, "elementReference") or "?"
    for c in v:
        return (c.text or "").strip()
    return "?"


def _filters(el) -> str:
    parts = [f"{_text(f, 'field')} {_text(f, 'operator')} {_value(f)}"
             for f in _kids(el, "filters")]
    return f" {(_text(el, 'filterLogic') or 'and').upper()} ".join(parts) or "none"


# ---------------------------------------------------------------- flow summary
def summarize_flow(xml_text: str, path: str) -> str:
    """A 2,000-line flow becomes the facts a reviewer needs: when it runs, what it writes."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        return f"Flow {path}: could not parse XML ({e})"
    lines = [f"Flow: {_text(root, 'label')} ({_text(root, 'processType')}, "
             f"status {_text(root, 'status') or '?'})"]
    start = next(iter(_kids(root, "start")), None)
    if start is not None and _text(start, "object"):
        lines.append(f"Runs: {_text(start, 'triggerType')} on {_text(start, 'object')} "
                     f"({_text(start, 'recordTriggerType')}); entry: {_filters(start)}")
    for kind, verb in (("recordUpdates", "UPDATES"), ("recordCreates", "CREATES"),
                       ("recordDeletes", "DELETES")):
        for el in _kids(root, kind):
            target = _text(el, "object") or _text(el, "inputReference") or "?"
            sets = ", ".join(f"{_text(a, 'field')} = {_value(a)}"
                             for a in _kids(el, "inputAssignments"))
            lines.append(f"- {verb} {target} in '{_text(el, 'name')}': "
                         f"{sets or '(fields from variable)'}; when {_filters(el)}")
    for kind in ("actionCalls", "subflows"):
        for el in _kids(root, kind):
            lines.append(f"- CALLS {kind[:-1]} {_text(el, 'actionName') or _text(el, 'flowName')}")
    counts = {}
    for c in root:
        counts[_local(c.tag)] = counts.get(_local(c.tag), 0) + 1
    other = ", ".join(f"{n} {k}" for k, n in sorted(counts.items())
                      if k in ("decisions", "assignments", "loops", "screens", "getRecords"))
    if other:
        lines.append(f"Also contains: {other} (logic not expanded here)")
    return "\n".join(lines)


# ---------------------------------------------------------------- permission summary
_BLOCK = re.compile(r"<(fieldPermissions|objectPermissions|userPermissions)>(.*?)</\1>", re.S)


def _perm_blocks(text: str) -> list[str]:
    out = []
    for kind, body in _BLOCK.findall(text):
        tag = lambda t: (re.search(f"<{t}>(.*?)</{t}>", body) or [None, "?"])[1]
        if kind == "fieldPermissions":
            access = "read+edit" if tag("editable") == "true" else \
                     "read" if tag("readable") == "true" else "none"
            out.append(f"FLS {tag('field')}: {access}")
        elif kind == "objectPermissions":
            flags = [f for f in ("Read", "Create", "Edit", "Delete")
                     if tag(f"allow{f}") == "true"]
            if tag("viewAllRecords") == "true":
                flags.append("ViewAll")
            if tag("modifyAllRecords") == "true":
                flags.append("ModifyAll")
            out.append(f"Object {tag('object')}: {', '.join(flags) or 'none'}")
        else:
            out.append(f"User permission {tag('name')}: {tag('enabled')}")
    return out


def summarize_permission_change(change: FileChange, full_tokens: int) -> str:
    """A 4,000-line profile diff becomes '+ FLS Opportunity.Discount_Percent__c: read+edit'."""
    added = _perm_blocks("\n".join(t for _, t in change.added))
    removed = _perm_blocks("\n".join(t for _, t in change.removed))
    lines = [f"{change.path} ({change.status}, full file ~{full_tokens:,} tokens). "
             f"Permission blocks changed in this PR:"]
    lines += [f"+ {b}" for b in added] + [f"- {b}" for b in removed]
    if not added and not removed:
        lines.append(f"(no complete permission blocks; {len(change.added)} lines added, "
                     f"{len(change.removed)} removed)")
    return "\n".join(lines)


def grants(xml_text: str, field_api: str) -> str | None:
    """Does this profile/permission set grant FLS on field_api? Returns the access level."""
    for b in _perm_blocks(xml_text):
        if b.startswith(f"FLS {field_api}:"):
            access = b.split(": ", 1)[1]
            return None if access == "none" else access
    return None


# ---------------------------------------------------------------- Apex references
APEX_BUILTINS = {
    "System", "Database", "Schema", "Limits", "Test", "Trigger", "UserInfo", "JSON",
    "String", "Integer", "Decimal", "Double", "Long", "Boolean", "Date", "Datetime",
    "Time", "Id", "Blob", "Math", "List", "Map", "Set", "Object", "Type", "Exception",
    "Http", "HttpRequest", "HttpResponse", "EncodingUtil", "Crypto", "Url", "Pattern",
    "Matcher", "Messaging", "Approval", "Search", "Security", "Auth", "Site", "Label",
    "ApexPages", "PageReference", "Queueable", "Database.Batchable", "Schedulable",
    "AggregateResult", "SObject", "Assert", "TestVisible", "IsTest", "AuraEnabled",
}

_REF = [
    re.compile(r"\bnew\s+([A-Z]\w*)\s*[(<\[]"),
    re.compile(r"\b([A-Z]\w*)\s*\.\s*[a-zA-Z_]\w*\s*\("),
    re.compile(r"\b(?:extends|implements)\s+([A-Z]\w*)"),
]
_COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)
_STRING = re.compile(r"'(?:\\.|[^'\\])*'")


def strip_noise(src: str) -> str:
    return _STRING.sub("''", _COMMENT.sub("", src))


def referenced_classes(src: str) -> set[str]:
    clean = strip_noise(src)
    names = {m for rx in _REF for m in rx.findall(clean)}
    return {n for n in names if n not in APEX_BUILTINS and not n.endswith("__c")}


_SIG = re.compile(r"^(?:public|global|private|protected|virtual|abstract|override|static|"
                  r"with sharing|without sharing|inherited sharing|@\w+)\b")


def signatures(src: str) -> str:
    """Class and method declarations only: the 'shape' of a class at ~10% of its size."""
    out = []
    for line in strip_noise(src).splitlines():
        s = line.strip()
        if s.startswith("@"):
            out.append(s)
        elif _SIG.match(s) and ("(" in s or " class " in f" {s} " or " interface " in f" {s} ") \
                and not s.endswith(";"):
            if s.endswith("{}"):
                out.append(s)
            else:
                out.append(s.rstrip("{").strip() + (" { ... }" if "(" in s else " {"))
    return "\n".join(out) + ("\n}" if out else "")
