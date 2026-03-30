"""
Codex-backed access to the Westbury papers database for JARVIS.

This module is intentionally narrow:
- ensure Codex can see the Westbury MCP server
- run a single GPT-5.4 Codex task against that MCP tool
- parse the structured result for JARVIS to summarize aloud
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

import httpx

log = logging.getLogger("jarvis.westbury")

CODEX_MODEL = "gpt-5.4"
CODEX_REASONING_EFFORT = "xhigh"
WESTBURY_MCP_NAME = os.environ.get("WESTBURY_MCP_NAME", "lightrag-westbury")
WESTBURY_QUERY_URL = os.environ.get("WESTBURY_QUERY_URL", "http://100.98.84.84:8001")
_BASE_DIR = Path(__file__).resolve().parent
_VSCODE_DIR = _BASE_DIR.parent
_DEFAULT_MCP_SCRIPT = _VSCODE_DIR / "rag_testing" / "mcp_server_westbury.py"
_DEFAULT_MCP_PYTHON = _VSCODE_DIR / "rag_testing" / "venv" / "bin" / "python"
WESTBURY_MCP_SCRIPT = Path(
    os.environ.get("WESTBURY_MCP_SCRIPT", str(_DEFAULT_MCP_SCRIPT))
).expanduser()
WESTBURY_MCP_PYTHON = Path(
    os.environ.get("WESTBURY_MCP_PYTHON", str(_DEFAULT_MCP_PYTHON))
).expanduser()
WESTBURY_WORK_DIR = _BASE_DIR / "data" / "westbury_codex"
WESTBURY_SCHEMA_FILE = WESTBURY_WORK_DIR / "response_schema.json"

RESULT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "answer": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "evidence": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 4,
        },
        "used_follow_up_queries": {"type": "boolean"},
        "follow_up_question": {"type": "string"},
    },
    "required": [
        "answer",
        "confidence",
        "evidence",
        "used_follow_up_queries",
        "follow_up_question",
    ],
}


@dataclass
class WestburyDatabaseResult:
    answer: str
    confidence: str
    evidence: list[str]
    used_follow_up_queries: bool
    follow_up_question: str
    raw_output: str = ""


def build_database_prompt(question: str) -> str:
    """Build the instruction block for a single Codex database query."""
    return f"""You are JARVIS's Westbury papers research specialist running inside Codex.

Your job is to answer the user's question using the Westbury MCP tool `query_westbury_papers`.

Rules:
- Use the Westbury MCP tool directly. Do not browse the web.
- Do not edit files or inspect the surrounding repository unless absolutely required.
- You may call the MCP tool multiple times.
- Start with `hybrid` unless a different mode is clearly better.
- If the first retrieval is too broad, refine the question and query again.
- If the question is about a specific paper, author, or concept, consider `local`.
- If the question is about broad themes or trends, consider `global`.
- If the database does not contain enough evidence, say so plainly.

Return JSON only, matching the provided schema.

User question:
{question}
"""


def build_codex_command(
    *,
    session_dir: Path,
    output_file: Path,
    schema_file: Path,
) -> list[str]:
    """Build the Codex CLI command for a database query."""
    return [
        "codex",
        "exec",
        "--full-auto",
        "--skip-git-repo-check",
        "-C",
        str(session_dir),
        "-m",
        CODEX_MODEL,
        "-c",
        f'model_reasoning_effort="{CODEX_REASONING_EFFORT}"',
        "-o",
        str(output_file),
        "--output-schema",
        str(schema_file),
        "-",
    ]


def parse_database_response(raw_text: str) -> WestburyDatabaseResult:
    """Parse the structured Codex response."""
    if not raw_text.strip():
        raise ValueError("Codex returned an empty database response")

    data = json.loads(raw_text)
    answer = " ".join(str(data.get("answer", "")).split())
    if not answer:
        raise ValueError("Codex database response did not contain an answer")

    confidence = str(data.get("confidence", "medium")).strip().lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "medium"

    evidence = [
        " ".join(str(item).split())
        for item in data.get("evidence", [])
        if str(item).strip()
    ]
    follow_up_question = " ".join(
        str(data.get("follow_up_question", "")).split()
    )

    return WestburyDatabaseResult(
        answer=answer,
        confidence=confidence,
        evidence=evidence,
        used_follow_up_queries=bool(data.get("used_follow_up_queries", False)),
        follow_up_question=follow_up_question,
        raw_output=raw_text,
    )


def _write_schema_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(RESULT_SCHEMA, indent=2))


async def _run_subprocess(
    *cmd: str,
    cwd: str | None = None,
    stdin_text: str | None = None,
    timeout: float = 60.0,
) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdin=asyncio.subprocess.PIPE if stdin_text is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(
        process.communicate(stdin_text.encode() if stdin_text is not None else None),
        timeout=timeout,
    )
    return process.returncode, stdout.decode().strip(), stderr.decode().strip()


async def get_westbury_status() -> dict:
    """Return readiness information for the settings panel and diagnostics."""
    codex_installed = shutil.which("codex") is not None
    script_exists = WESTBURY_MCP_SCRIPT.exists()
    python_exists = WESTBURY_MCP_PYTHON.exists()
    mcp_configured = False
    reachable = False
    llm_name = ""

    if codex_installed:
        try:
            rc, _, _ = await _run_subprocess(
                "codex", "mcp", "get", WESTBURY_MCP_NAME, timeout=10.0
            )
            mcp_configured = rc == 0
        except Exception:
            mcp_configured = False

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{WESTBURY_QUERY_URL}/health")
            if resp.status_code == 200:
                body = resp.json()
                reachable = True
                llm_name = str(body.get("llm", ""))
    except Exception:
        reachable = False

    return {
        "codex_installed": codex_installed,
        "westbury_mcp_configured": mcp_configured,
        "westbury_server_reachable": reachable,
        "westbury_mcp_script_exists": script_exists,
        "westbury_mcp_python_exists": python_exists,
        "westbury_query_url": WESTBURY_QUERY_URL,
        "westbury_server_llm": llm_name,
    }


async def ensure_westbury_mcp() -> None:
    """Register the Westbury MCP server with Codex if needed."""
    codex_path = shutil.which("codex")
    if not codex_path:
        raise RuntimeError("Codex CLI is not installed.")
    if not WESTBURY_MCP_SCRIPT.exists():
        raise RuntimeError(f"Westbury MCP script not found at {WESTBURY_MCP_SCRIPT}")
    if not WESTBURY_MCP_PYTHON.exists():
        raise RuntimeError(f"Westbury MCP Python not found at {WESTBURY_MCP_PYTHON}")

    rc, _, _ = await _run_subprocess(
        codex_path, "mcp", "get", WESTBURY_MCP_NAME, timeout=10.0
    )
    if rc == 0:
        return

    log.info("Registering Westbury MCP server with Codex")
    rc, stdout, stderr = await _run_subprocess(
        codex_path,
        "mcp",
        "add",
        WESTBURY_MCP_NAME,
        "--env",
        f"WESTBURY_QUERY_URL={WESTBURY_QUERY_URL}",
        "--",
        str(WESTBURY_MCP_PYTHON),
        str(WESTBURY_MCP_SCRIPT),
        timeout=30.0,
    )
    if rc != 0:
        detail = stderr or stdout or "Unknown Codex MCP registration error"
        raise RuntimeError(f"Failed to register Westbury MCP with Codex: {detail}")


async def run_database_query(question: str) -> WestburyDatabaseResult:
    """Run a single Westbury database query through Codex."""
    status = await get_westbury_status()
    if not status["codex_installed"]:
        raise RuntimeError("Codex CLI is not installed.")
    if not status["westbury_server_reachable"]:
        raise RuntimeError(
            f"Westbury query server is unreachable at {WESTBURY_QUERY_URL}"
        )

    await ensure_westbury_mcp()

    WESTBURY_WORK_DIR.mkdir(parents=True, exist_ok=True)
    _write_schema_file(WESTBURY_SCHEMA_FILE)

    prompt = build_database_prompt(question)
    output_file = WESTBURY_WORK_DIR / f"codex_result_{uuid.uuid4().hex}.json"
    output_file.unlink(missing_ok=True)

    cmd = build_codex_command(
        session_dir=WESTBURY_WORK_DIR,
        output_file=output_file,
        schema_file=WESTBURY_SCHEMA_FILE,
    )
    log.info("Running Westbury database query via Codex")
    rc, stdout, stderr = await _run_subprocess(
        *cmd,
        cwd=str(WESTBURY_WORK_DIR),
        stdin_text=prompt,
        timeout=420.0,
    )

    raw_text = ""
    if output_file.exists():
        raw_text = output_file.read_text().strip()
    elif stdout:
        raw_text = stdout.strip()

    try:
        if rc != 0:
            detail = stderr or stdout or "Codex exited with a non-zero status"
            raise RuntimeError(detail)
        return parse_database_response(raw_text)
    finally:
        try:
            output_file.unlink(missing_ok=True)
        except Exception:
            pass
