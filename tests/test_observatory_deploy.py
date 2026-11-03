"""Synthetic tier

Deployment-template contract tests for the MedRadar Observatory supervisor files.

These checks are offline and deterministic. They prove (a) the deliverable files
exist, (b) the systemd unit keeps its documented contract (graceful SIGTERM,
restart, resource limits, sandbox, journald, the real CLI command, no committed
secret), (c) the timer really is a persistent 6-hourly schedule, (d) the
PowerShell scripts are syntactically valid, (e) `install_windows_task.ps1 -WhatIf`
prints the exact command and registers nothing, and (f) no file commits a value
for MEDRADAR_SEC_UA.

Additional contracts enforced here: the systemd ExecStart parses against the real
CLI, and the Windows scheduled action is **one-shot** (`-MaxCycles 1`, one pass per
trigger) because a Task Scheduler forced end cannot cleanly stop a long-running
child python collector; the long-running watcher remains for interactive use.

They do NOT prove that anything is deployed: no systemd unit runs and no scheduled
task is created here. Deployment status stays NOT_DEPLOYED until a supervisor is
installed and verified by the operator/Lead (docs/RELIABILITY_DESIGN.md §0, §3).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

DELIVERABLES = {
    "deploy/systemd/medradar-observatory.service": "Linux long-running collector unit",
    "deploy/systemd/medradar-observatory.timer": "6-hourly one-shot timer",
    "deploy/systemd/README.md": "systemd operation guide",
    "deploy/windows/README.md": "Windows Task Scheduler operation guide",
    "scripts/observatory_watch.ps1": "Windows dev/ops watcher",
    "scripts/install_windows_task.ps1": "Task Scheduler installer",
    "scripts/uninstall_windows_task.ps1": "Task Scheduler uninstaller",
    "docs/DEPLOYMENT.md": "operator runbook",
}

SYSTEMD_UNIT = "deploy/systemd/medradar-observatory.service"
SYSTEMD_TIMER = "deploy/systemd/medradar-observatory.timer"
POWERSHELL_SCRIPTS = [
    "scripts/observatory_watch.ps1",
    "scripts/install_windows_task.ps1",
    "scripts/uninstall_windows_task.ps1",
]

TASK_NAME = "MedRadarObservatory"


# --------------------------------------------------------------------- helpers
def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def _powershell_exe() -> str | None:
    """Locate a PowerShell host: powershell.exe first on Windows, pwsh elsewhere."""
    candidates = ("powershell", "pwsh") if os.name == "nt" else ("pwsh", "powershell")
    for name in candidates:
        found = shutil.which(name)
        if found:
            return found
    return None


def _run(command: list[str], timeout: float = 180.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
    )


# ------------------------------------------------------------------- (a) files
@pytest.mark.parametrize("relative", sorted(DELIVERABLES))
def test_deliverable_exists_and_is_non_empty(relative: str) -> None:
    path = REPO_ROOT / relative
    assert path.is_file(), f"missing deliverable: {relative} ({DELIVERABLES[relative]})"
    assert path.stat().st_size > 0, f"empty deliverable: {relative}"


# -------------------------------------------------------------------- (b) unit
SECRET_LOOKING_PATTERNS = [
    # credential assignments that are not env-var references
    re.compile(
        r"(?im)^\s*\w*(?:api[_-]?key|secret|password|passwd|token)\w*\s*[:=]\s*"
        r"(?P<value>(?!\$|\$\{|%|<)[^\s#]+)"
    ),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]


def _assert_no_committed_secret(relative: str) -> None:
    text = _read(relative)
    for pattern in SECRET_LOOKING_PATTERNS:
        match = pattern.search(text)
        assert match is None, (
            f"{relative} looks like it contains a committed secret: "
            f"{match.group(0)!r} - credentials/contact addresses must come from an env file"
        )


def test_systemd_unit_keeps_required_contract() -> None:
    unit = _read(SYSTEMD_UNIT)

    required_lines = [
        "WorkingDirectory=/srv/medradar",
        "Restart=always",
        "RestartSec=30",
        "TimeoutStopSec=120",
        "KillSignal=SIGTERM",
        "MemoryMax=512M",
        "CPUQuota=50%",
        "NoNewPrivileges=true",
        "PrivateTmp=true",
        "ProtectSystem=strict",
        "ReadWritePaths=/srv/medradar",
        "StandardOutput=journal",
        "StandardError=journal",
    ]
    for required in required_lines:
        assert re.search(rf"(?m)^\s*{re.escape(required)}\s*$", unit), (
            f"systemd unit is missing the required directive: {required}"
        )

    # Optional env file (leading '-') so the unit starts before the operator
    # creates it; the SEC User-Agent must never be a hard-coded production value.
    assert re.search(
        r"(?m)^\s*EnvironmentFile=-/etc/medradar/observatory\.env\s*$", unit
    ), "unit must read EnvironmentFile=-/etc/medradar/observatory.env"

    # ExecStart must invoke the real CLI, not an invented wrapper.
    exec_start = [
        line.strip() for line in unit.splitlines() if line.strip().startswith("ExecStart=")
    ]
    assert len(exec_start) == 1, "unit must have exactly one ExecStart="
    command = exec_start[0]
    assert "-m medradar observatory watch" in command, (
        f"ExecStart does not run the real CLI subcommand 'observatory watch': {command}"
    )
    for expected in (
        "--interval-minutes 60",
        "--trigger schedule",
        "--log-file /srv/medradar/logs/collector.log",
    ):
        assert expected in command, f"ExecStart is missing documented option {expected!r}"
    assert command.startswith("ExecStart=/"), "ExecStart should call an absolute interpreter path"

    # ExecStartPre must also use the real CLI (a readiness probe), never a fake flag.
    exec_pre = [
        line.strip() for line in unit.splitlines() if line.strip().startswith("ExecStartPre=")
    ]
    assert any("-m medradar observatory" in line for line in exec_pre), (
        "ExecStartPre should exercise the real `python -m medradar observatory` CLI"
    )

    _assert_no_committed_secret(SYSTEMD_UNIT)
    # The unit documents the env-file requirement; it must not set the UA itself.
    assert re.search(r"(?m)^\s*Environment=MEDRADAR_SEC_UA=", unit) is None
    assert "MEDRADAR_SEC_UA=" not in unit


def test_supervisor_command_is_accepted_by_the_real_cli() -> None:
    """The unit's ExecStart must parse against the actual ``medradar`` CLI.

    Parsing only: nothing is executed and no ledger is touched. This is the
    template-vs-CLI contract (docs/RELIABILITY_DESIGN.md §3): if a flag used by
    the supervisor templates disappears from the real CLI, this test fails.
    """
    import shlex

    from medradar.__main__ import build_parser

    unit = _read(SYSTEMD_UNIT)
    exec_start = next(
        line.strip() for line in unit.splitlines() if line.strip().startswith("ExecStart=")
    )
    words = shlex.split(exec_start[len("ExecStart=") :])
    assert words[0].endswith("python3"), f"unexpected ExecStart interpreter: {words[0]}"
    assert words[1:3] == ["-m", "medradar"], "ExecStart must run `python -m medradar`"
    cli_argv = words[3:]

    parser = build_parser()
    namespace = parser.parse_args(cli_argv)
    assert namespace.command == "observatory"
    assert namespace.obs_action == "watch"
    assert float(namespace.interval_minutes) == 60.0
    assert namespace.trigger == "schedule"
    assert namespace.log_file == "/srv/medradar/logs/collector.log"

    # The commands the docs tell operators to run must exist on this branch too.
    parser.parse_args(["observatory", "health", "--json"])
    parser.parse_args(
        ["observatory", "deploy-status", "--status", "DEPLOYED_LOCAL", "--supervisor", "windows_task"]
    )
    parser.parse_args(["observatory", "lock", "status"])


def test_documented_commands_in_templates_are_real() -> None:
    """Docs reference the commands that exist on this branch and no invented ones."""
    docs = "\n".join(
        _read(path)
        for path in (
            "deploy/systemd/README.md",
            "deploy/windows/README.md",
            "docs/DEPLOYMENT.md",
        )
    )
    for command in (
        "observatory watch",
        "observatory sync",
        "observatory status",
        "observatory pause",
        "observatory resume",
        "observatory health --json",
        "observatory deploy-status",
        "observatory lock status",
        "observatory lock release",
    ):
        assert command in docs, f"deployment docs do not reference the real command: {command}"


# ------------------------------------------------------------------- (c) timer
def test_timer_is_persistent_six_hourly_schedule() -> None:
    timer = _read(SYSTEMD_TIMER)

    assert re.search(r"(?m)^\s*\[Timer\]\s*$", timer), "timer file needs a [Timer] section"
    assert re.search(r"(?m)^\s*Persistent=true\s*$", timer), (
        "timer must set Persistent=true so a missed 6-hourly slot runs on boot"
    )
    assert re.search(r"(?m)^\s*RandomizedDelaySec=120\s*$", timer), (
        "timer must set RandomizedDelaySec=120"
    )
    on_calendar = [
        line.strip() for line in timer.splitlines() if line.strip().startswith("OnCalendar=")
    ]
    assert len(on_calendar) == 1, "timer must have exactly one OnCalendar="
    # 6-hourly at :17 -> systemd step syntax 00/6
    assert re.search(r"OnCalendar=\*-\*-\*\s+00/6:17:00\b", on_calendar[0]), (
        f"timer is not a 6-hourly schedule: {on_calendar[0]}"
    )
    assert re.search(r"(?m)^\s*Unit=medradar-observatory\.service\s*$", timer), (
        "timer must activate medradar-observatory.service"
    )
    assert "timers.target" in timer, "timer must be enabled under timers.target"


# ------------------------------------------------------------ (d) script parse
@pytest.mark.parametrize("relative", POWERSHELL_SCRIPTS)
def test_powershell_scripts_parse(relative: str) -> None:
    powershell = _powershell_exe()
    if powershell is None:
        pytest.skip("PowerShell is not installed on this host (CI Linux): parse check skipped")

    script_path = (REPO_ROOT / relative).resolve()
    assert script_path.is_file(), f"missing script: {relative}"
    quoted = str(script_path).replace("'", "''")
    # Deliberately the same construct required by the deployment contract: a
    # full-file parse into a scriptblock, without executing anything.
    command = (
        "& { [scriptblock]::Create((Get-Content -Raw -LiteralPath "
        f"'{quoted}')) | Out-Null }}"
    )
    result = _run([powershell, "-NoProfile", "-Command", command])
    assert result.returncode == 0, (
        f"{relative} does not parse as PowerShell.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


# ------------------------------------- (d2) Windows task = one-shot timer mode
def test_windows_task_registers_one_shot_mode() -> None:
    """The scheduled task must run one pass per trigger, and the docs must say why.

    Context: on Windows a forced task end (schtasks /End) can terminate the
    PowerShell wrapper while a long-running python collector survives and keeps
    the ledger lease. The scheduled action therefore passes -MaxCycles 1; the
    long-running watcher stays available for interactive terminal use.
    """
    installer = _read("scripts/install_windows_task.ps1")
    watcher = _read("scripts/observatory_watch.ps1")
    windows_readme = _read("deploy/windows/README.md")
    deployment = _read("docs/DEPLOYMENT.md")

    assert "-MaxCycles 1" in installer, (
        "installer must pass -MaxCycles 1 so each trigger runs exactly one collection pass"
    )
    assert "$MaxCycles" in watcher and "--max-cycles" in watcher, (
        "watcher must keep the -MaxCycles parameter for one-shot mode"
    )
    for phrase in ("one-shot", "cannot cleanly stop", "ledger lease"):
        assert phrase in windows_readme, (
            f"deploy/windows/README.md must document the one-shot rationale ({phrase!r})"
        )
    assert "--max-cycles 1" in deployment, (
        "docs/DEPLOYMENT.md must document the one-shot command used by the Windows task"
    )
    assert "forced task end" in deployment, (
        "docs/DEPLOYMENT.md must document why the scheduled watcher is one-shot"
    )


# --------------------------------------------- (e) installer -WhatIf is a no-op
def _schtasks_query() -> subprocess.CompletedProcess[str] | None:
    schtasks = shutil.which("schtasks")
    if schtasks is None:
        return None
    return _run([schtasks, "/Query", "/TN", TASK_NAME], timeout=60.0)


def test_installer_whatif_prints_one_shot_action() -> None:
    """-WhatIf always prints the one-shot action, with or without an existing task.

    This runs even when a real task is registered by an operator (the -WhatIf path
    never modifies it), so the one-shot contract is exercised on this host.
    """
    if os.name != "nt":
        pytest.skip("Windows Task Scheduler installer is Windows-only (CI Linux)")
    powershell = _powershell_exe()
    if powershell is None:
        pytest.skip("PowerShell is not installed on this host")

    installer = REPO_ROOT / "scripts" / "install_windows_task.ps1"
    result = _run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(installer),
            "-WhatIf",
        ]
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, f"installer -WhatIf failed:\n{output}"
    assert "Register-ScheduledTask" in output, f"-WhatIf did not print the command:\n{output}"
    assert "-MaxCycles 1" in output, (
        f"the registered action must pass -MaxCycles 1 (one pass per trigger):\n{output}"
    )
    assert "one-shot" in output.lower(), (
        f"-WhatIf should state that the task runs one-shot:\n{output}"
    )


def test_installer_whatif_prints_command_and_creates_nothing() -> None:
    if os.name != "nt":
        pytest.skip("Windows Task Scheduler is not available on this host (CI Linux)")
    powershell = _powershell_exe()
    if powershell is None:
        pytest.skip("PowerShell is not installed on this host")

    before = _schtasks_query()
    if before is None:
        pytest.skip("schtasks.exe is not available; cannot verify task registration")
    if before.returncode == 0:
        pytest.skip(
            f"a task registered by an operator already exists ({TASK_NAME!r}); "
            "-WhatIf does not modify it, so this test cannot assert that -WhatIf "
            "created nothing on this host"
        )

    installer = REPO_ROOT / "scripts" / "install_windows_task.ps1"
    result = _run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(installer),
            "-WhatIf",
        ]
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, f"installer -WhatIf failed:\n{output}"
    assert "Register-ScheduledTask" in output, (
        f"installer -WhatIf did not print the exact Register-ScheduledTask command:\n{output}"
    )
    assert TASK_NAME in output, "installer -WhatIf did not name the task it would register"
    assert "nothing was registered" in output.lower() or "nothing was changed" in output.lower(), (
        "installer -WhatIf should say explicitly that nothing was created"
    )

    after = _schtasks_query()
    assert after is not None, "schtasks became unavailable during the test"
    assert after.returncode != 0, (
        f"task {TASK_NAME!r} exists after a -WhatIf run; -WhatIf must create nothing.\n"
        f"schtasks stdout:\n{after.stdout}\nstderr:\n{after.stderr}"
    )


# ------------------------------------------------ (f) no committed SEC UA value
def test_no_committed_sec_ua_value() -> None:
    """MEDRADAR_SEC_UA may appear as a name, never as a committed production value.

    Documented placeholders (`<...>`) and environment-variable references are
    fine; a literal contact address or credential is not, and the tests also
    reject an embedded '@' so a personal address cannot slip in.
    """
    assignment = re.compile(r"MEDRADAR_SEC_UA\s*=\s*(?P<value>.+)$", re.MULTILINE)

    checked = 0
    for relative in DELIVERABLES:
        text = _read(relative)
        for match in assignment.finditer(text):
            checked += 1
            value = match.group("value").strip()
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
            value = value.strip("\"'").strip()
            is_env_reference = value.startswith("$") or value.startswith("%")
            is_placeholder = ("<" in value and ">" in value) or value in {"...", ""}
            assert is_env_reference or is_placeholder, (
                f"{relative} assigns MEDRADAR_SEC_UA a non-reference value: {value!r}; "
                "credentials/contact addresses must come from the environment only"
            )
            assert "@" not in value, (
                f"{relative} commits an email/contact address in MEDRADAR_SEC_UA: {value!r}"
            )
    # Zero assignments is the expected state today (no committed secrets). If one
    # is ever added above, the loop still enforces that it is a reference/placeholder
    # and never a real address. `checked` exists so the intent is explicit and a
    # future reader can log/inspect the count if the invariant is ever extended.
    assert checked >= 0
