"""
Workflow definitions — expressed as DATA, not code. Lives in shared because both
the worker (to seed/execute) and the API (to create runs) need it.

`type` strings match awp_shared.enums.StepType values ("llm"/"tool"/"approval"/"router").
"""

RESEARCH_V1 = {
    "slug": "research_v1",
    "name": "Competitor research",
    "steps": [
        {"name": "parse_request", "type": "llm",
         "instruction": "Restate the user's research goal in one sentence, then list 3-5 "
                        "specific things to look for. Be concise."},
        {"name": "search_web", "type": "tool", "tool": "web_search"},
        {"name": "summarize", "type": "llm",
         "instruction": "Using the web_search results in the context, write a concise "
                        "comparison of the options relevant to the user's goal. Cite the "
                        "tool/product names. Do not invent options not present in the results."},
        {"name": "human_approval", "type": "approval"},
        {"name": "final_answer", "type": "llm",
         "instruction": "Write the final answer for the user: a clear, well-structured "
                        "response that draws on the summary and search results in the context."},
    ],
}

# Registry so callers can look up a definition by slug.
WORKFLOWS = {RESEARCH_V1["slug"]: RESEARCH_V1}
