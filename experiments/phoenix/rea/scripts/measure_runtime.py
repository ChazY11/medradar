"""PHOENIX-001 REA validation: runtime metrics harness.

Measures, against the pinned REA 6.7.0 deployment in D:\\DEPPSKK\\.rea:

  * CLI startup latency        (`rea --version`)                x3, median
  * MCP doctor latency         (`rea mcp doctor --json`)         x3, median
  * MCP server cold start      spawn -> initialize response      x3, median
  * tools/list latency         initialize -> 207 tools returned  x3, median
  * peak working set (RSS)     PSAPI GetProcessMemoryInfo PeakWorkingSetSize
  * outbound TCP endpoints     `netstat -ano` sampled during the session

Raw JSON-RPC over stdio is used (newline-delimited), which is exactly the MCP
stdio framing DSH would use. Nothing is written outside this experiment folder.

Writes: evidence/runtime_metrics.json
"""

import ctypes
import ctypes.wintypes as wt
import json
import os
import subprocess
import sys
import time

REA_ROOT = r"D:\DEPPSKK\.rea"
SERVER = os.path.join(REA_ROOT, "node_modules", "rea-agents", "scripts", "rea.mjs")
REA_CMD = os.path.join(REA_ROOT, "node_modules", ".bin", "rea.cmd")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "evidence",
                   "runtime_metrics.json")

INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-11-25",
        "capabilities": {},
        "clientInfo": {"name": "phoenix-001-measure", "version": "0.1.0"},
    },
}
INITIALIZED = {"jsonrpc": "2.0", "method": "notifications/initialized"}
LIST_TOOLS = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}

# --- Windows memory counters -------------------------------------------------
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", wt.DWORD),
        ("PageFaultCount", wt.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def peak_rss_bytes(pid):
    """Return (current WorkingSetSize, PeakWorkingSetSize) in bytes, or None."""
    try:
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return None
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        ok = ctypes.windll.psapi.GetProcessMemoryInfo(
            handle, ctypes.byref(counters), counters.cb)
        ctypes.windll.kernel32.CloseHandle(handle)
        if not ok:
            return None
        return counters.WorkingSetSize, counters.PeakWorkingSetSize
    except Exception:
        return None


def tcp_endpoints_for_pid(pid):
    """Parse `netstat -ano` and return remote endpoints owned by pid."""
    try:
        out = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True, text=True, timeout=20,
            creationflags=subprocess.CREATE_NO_WINDOW,
        ).stdout
    except Exception:
        return []
    rows = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0].upper() != "TCP":
            continue
        local, remote, state, owner = parts[1], parts[2], parts[3], parts[4]
        if owner != str(pid):
            continue
        rows.append({"local": local, "remote": remote, "state": state})
    return rows


def send(proc, obj):
    proc.stdin.write((json.dumps(obj) + "\n").encode("utf-8"))
    proc.stdin.flush()


def read_message(proc, timeout_s):
    """Read one newline-delimited JSON-RPC message."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            return None
        text = line.decode("utf-8", "replace").strip()
        if not text:
            continue
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            continue
    return None


def measure_mcp(round_index):
    """Spawn the MCP server and time spawn->initialize->tools/list."""
    node = "node"
    t0 = time.perf_counter()
    proc = subprocess.Popen(
        [node, SERVER, "mcp"],
        cwd=REA_ROOT,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )

    send(proc, INIT)
    init_resp = read_message(proc, 60)
    t_init = time.perf_counter()
    if init_resp is None:
        raise RuntimeError("no initialize response")

    send(proc, INITIALIZED)
    send(proc, LIST_TOOLS)
    list_resp = read_message(proc, 60)
    t_list = time.perf_counter()
    if list_resp is None:
        raise RuntimeError("no tools/list response")

    tools = list_resp.get("result", {}).get("tools", [])
    rss = peak_rss_bytes(proc.pid)
    endpoints = tcp_endpoints_for_pid(proc.pid)
    try:
        proc.stdin.close()
    except Exception:
        pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    err = proc.stderr.read().decode("utf-8", "replace")

    return {
        "round": round_index,
        "spawn_to_initialize_ms": round((t_init - t0) * 1000, 1),
        "initialize_to_tools_list_ms": round((t_list - t_init) * 1000, 1),
        "spawn_to_tools_list_ms": round((t_list - t0) * 1000, 1),
        "server_info": init_resp.get("result", {}).get("serverInfo"),
        "protocol_version": init_resp.get("result", {}).get("protocolVersion"),
        "tool_count": len(tools),
        "rss_bytes": rss[0] if rss else None,
        "peak_rss_bytes": rss[1] if rss else None,
        "tcp_endpoints": endpoints,
        "stderr_bytes": len(err),
    }


def measure_cli(args, timeout=120, parse_json=False):
    t0 = time.perf_counter()
    proc = subprocess.run(
        [REA_CMD] + args,
        cwd=REA_ROOT, capture_output=True, timeout=timeout,
        creationflags=subprocess.CREATE_NO_WINDOW,
        shell=False,
    )
    elapsed = (time.perf_counter() - t0) * 1000
    rec = {
        "argv": ["rea"] + args,
        "exit_code": proc.returncode,
        "ms": round(elapsed, 1),
        "stdout_bytes": len(proc.stdout),
        "stderr_bytes": len(proc.stderr),
    }
    if parse_json:
        try:
            body = json.loads(proc.stdout.decode("utf-8", "replace"))
            rec["parsed"] = {
                "healthy": body.get("healthy"),
                "adapter": body.get("adapter"),
                "server": body.get("server"),
                "tools": body.get("inventory", {}).get("tools"),
                "prompts": body.get("inventory", {}).get("prompts"),
            }
        except Exception as exc:  # noqa: BLE001 - recorded, never raised
            rec["parse_error"] = str(exc)
    return rec


def median(values):
    values = sorted(values)
    n = len(values)
    if n == 0:
        return None
    if n % 2:
        return values[n // 2]
    return round((values[n // 2 - 1] + values[n // 2]) / 2, 1)


def main():
    result = {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "node": subprocess.run(["node", "--version"], capture_output=True, text=True).stdout.strip(),
        "rea_package_version": None,
        "cli_version": [],
        "cli_doctor": [],
        "mcp": [],
    }

    pkg = json.load(open(os.path.join(REA_ROOT, "node_modules", "rea-agents", "package.json"),
                         encoding="utf-8"))
    result["rea_package_version"] = pkg["version"]

    for i in range(3):
        result["cli_version"].append(measure_cli(["--version"]))
        print("cli --version", result["cli_version"][-1], file=sys.stderr)

    for i in range(3):
        rec = measure_cli(["mcp", "doctor", "--json"], parse_json=True)
        result["cli_doctor"].append(rec)
        print("cli mcp doctor", rec, file=sys.stderr)

    for i in range(3):
        rec = measure_mcp(i + 1)
        result["mcp"].append(rec)
        print("mcp round", rec, file=sys.stderr)

    result["medians"] = {
        "cli_version_ms": median([r["ms"] for r in result["cli_version"]]),
        "cli_doctor_ms": median([r["ms"] for r in result["cli_doctor"]]),
        "mcp_spawn_to_initialize_ms": median(
            [r["spawn_to_initialize_ms"] for r in result["mcp"]]),
        "mcp_spawn_to_tools_list_ms": median(
            [r["spawn_to_tools_list_ms"] for r in result["mcp"]]),
        "peak_rss_bytes": median([r["peak_rss_bytes"] for r in result["mcp"]
                                  if r["peak_rss_bytes"]]),
        "tool_count": result["mcp"][0]["tool_count"] if result["mcp"] else None,
        "protocol_version": result["mcp"][0]["protocol_version"] if result["mcp"] else None,
    }
    result["medians"]["peak_rss_mb"] = round(result["medians"]["peak_rss_bytes"] / (1024 * 1024), 1)

    distinct_remotes = sorted({
        ep["remote"] for r in result["mcp"] for ep in (r.get("tcp_endpoints") or [])
    })
    result["observed_tcp_remotes"] = distinct_remotes

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    print(json.dumps(result["medians"], indent=2))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
