"""Tool JSON schemas and per-role permissions."""

READ_ONLY_TOOLS = {"read_file", "list_files"}  # the only tools offered in step 1 of a developer cycle

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List the entries (files and directories) of a directory in the repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory relative to the repo root. Defaults to '.'.",
                        "default": ".",
                    },
                    "reasoning": {"type": "string", "description": "Brief justification for this tool call"},
                },
                "required": ["reasoning"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to the repo root."},
                    "reasoning": {"type": "string", "description": "Brief justification for this tool call"},
                },
                "required": ["path", "reasoning"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_patch",
            "description": "Propose the full new content of a file; returns a unified diff.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "Path relative to the repo root."},
                    "new_content": {"type": "string", "description": "Full new content of the file."},
                    "reasoning": {"type": "string", "description": "Brief justification for this tool call"},
                },
                "required": ["file", "new_content", "reasoning"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_tests",
            "description": "Run the test suite and return whether it passed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reasoning": {"type": "string", "description": "Brief justification for this tool call"},
                },
                "required": ["reasoning"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_triage",
            "description": "Final decision of the triage: is the issue viable for an automated fix?",
            "parameters": {
                "type": "object",
                "properties": {
                    "verdict": {"type": "string", "enum": ["viable", "not_viable"]},
                    "reason": {"type": "string", "description": "Why the issue is or is not viable."},
                    "reasoning": {"type": "string", "description": "Brief justification for this tool call"},
                },
                "required": ["verdict", "reason", "reasoning"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_verdict",
            "description": "Final review verdict on the developer's patch.",
            "parameters": {
                "type": "object",
                "properties": {
                    "verdict": {"type": "string", "enum": ["approved", "changes_requested"]},
                    "reason": {"type": "string", "description": "Why the patch is approved or needs changes."},
                    "reasoning": {"type": "string", "description": "Brief justification for this tool call"},
                },
                "required": ["verdict", "reason", "reasoning"],
            },
        },
    },
]

TOOLS_BY_NAME = {t["function"]["name"]: t for t in TOOLS}

# Role permissions = which tools each role is OFFERED (and allowed to execute) in its cycle.
# Not enforced at DB level (future work). "coder" is the legacy single-role agent used by evals.
DECISION_TOOLS = {"submit_triage": {"viable", "not_viable"}, "submit_verdict": {"approved", "changes_requested"}}
ROLE_TOOLS = {
    "coder": ["list_files", "read_file", "propose_patch", "run_tests"],
    "developer": ["list_files", "read_file", "propose_patch", "run_tests"],
    "triage": ["list_files", "read_file", "submit_triage"],
    "reviewer": ["list_files", "read_file", "run_tests", "submit_verdict"],  # no propose_patch
}
