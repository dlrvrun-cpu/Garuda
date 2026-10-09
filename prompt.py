# garuda/prompt.py — what every Garuda agent shares, whatever the framework
from pydantic import BaseModel

SYSTEM_PROMPT = """You are Garuda, an expert Salesforce code reviewer.
Your only job right now: find SOQL injection in Apex code.
SOQL injection = user-controlled input reaching a dynamic query
(Database.query, Database.countQuery, Search.query) without binding
or String.escapeSingleQuotes."""


class Comment(BaseModel):
    file: str
    line: int
    severity: str
    message: str
    code: str


class Review(BaseModel):
    summary: str
    comments: list[Comment]


def build_user_msg(diff: str, context: str = "") -> str:
    msg = f"## Diff:\n```diff\n{diff}\n```"
    if context:
        msg += f"\n\n## Context:\n{context}"
    return msg
