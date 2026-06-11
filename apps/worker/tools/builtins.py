"""Built-in tools. web_search + email_draft are mocks; calculator + http are real."""
from tools.registry import register


class Calculator:
    name = "calculator"

    def run(self, payload: dict) -> dict:
        expr = str(payload.get("expression") or payload.get("query") or "")
        # Arithmetic only — restrict to a safe character set. A production tool
        # would use a real expression parser, not eval.
        if not set(expr) <= set("0123456789+-*/(). %"):
            raise ValueError("unsupported characters in expression")
        return {"result": eval(expr)}  # noqa: S307 (guarded by the allowlist above)


class WebSearchMock:
    name = "web_search"

    def run(self, payload: dict) -> dict:
        # Return only retrieved results (no echo of the query) so evals fact-check
        # against actual data, not the input.
        return {
            "results": [
                {"title": "Asana", "url": "https://asana.com", "snippet": "PM for teams."},
                {"title": "Trello", "url": "https://trello.com", "snippet": "Kanban boards."},
                {"title": "ClickUp", "url": "https://clickup.com", "snippet": "All-in-one PM."},
            ],
        }


class EmailDraftMock:
    name = "email_draft"

    def run(self, payload: dict) -> dict:
        return {"subject": "Draft", "body": f"Draft email about: {payload.get('query', '')}"}


class HttpRequestTool:
    name = "http_request"

    def run(self, payload: dict) -> dict:
        import urllib.request
        with urllib.request.urlopen(payload["url"], timeout=10) as r:
            return {"status": r.status, "body": r.read(500).decode("utf-8", "replace")}


for _t in (Calculator(), WebSearchMock(), EmailDraftMock(), HttpRequestTool()):
    register(_t)