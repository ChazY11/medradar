"""Verify the CUDA stack by doing real tensor computation (not just reading nvidia-smi).

``nvidia-smi`` proves a driver exists; it does not prove that PyTorch can allocate on
this GPU, that the wheel was built for the right compute capability, that kernels
actually execute, or that a bf16 matmul produces the right numbers on Blackwell
(sm_120).  This script checks all four, and records the measured answers.

Checks
------
1. ``torch.cuda.is_available()`` and a real device context.
2. Reported compute capability equals the expected ``(12, 0)`` for an RTX 5080 Laptop.
3. A 1024x1024 matmul runs on the GPU and its result matches a CPU reference
   (``torch.allclose`` with a stated tolerance) -- a wrong-arch binary or a broken
   kernel would fail here, not merely be slow.
4. bfloat16 matmul, if the device claims support, is also checked against float32.
5. A small optimization step runs (forward + backward + Adam step) and the parameter
   actually changes -- the cheapest proof that autograd kernels work on this arch.
6. Peak allocatable memory and a rough measured matmul throughput.

Exit code 0 only if every check passes.  Writes JSON when ``--out`` is given.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Sequence

EXPECTED_CAPABILITY = (12, 0)
_MIB = 1024.0 * 1024.0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=None)
    parser.add_argument("--size", type=int, default=1024)
    parser.add_argument("--iters", type=int, default=20)
    args = parser.parse_args(argv)

    import torch

    checks: list[dict[str, Any]] = []
    payload: dict[str, Any] = {
        "torch_version": torch.__version__,
        "torch_cuda_version": torch.version.cuda,
        "cudnn_version": torch.backends.cudnn.version() if torch.backends.cudnn.is_available() else None,
        "python": sys.version.split()[0],
        "checks": checks,
    }

    def record(name: str, passed: bool, detail: Any) -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})
        print(f"[{'PASS' if passed else 'FAIL'}] {name}: {detail}", flush=True)

    if not torch.cuda.is_available():
        record("cuda_available", False, "torch.cuda.is_available() is False")
        payload["verdict"] = "FAILED"
        _write(args.out, payload)
        return 1
    record("cuda_available", True, True)

    device = torch.device("cuda:0")
    capability = torch.cuda.get_device_capability(0)
    record("compute_capability", tuple(capability) == EXPECTED_CAPABILITY,
           {"reported": list(capability), "expected": list(EXPECTED_CAPABILITY)})
    properties = torch.cuda.get_device_properties(0)
    payload.update(
        {
            "device_name": properties.name,
            "vram_total_mib": round(properties.total_memory / _MIB, 0),
            "multiprocessor_count": properties.multi_processor_count,
        }
    )
    free_bytes, total_bytes = torch.cuda.mem_get_info(0)
    record("memory_info", total_bytes > 0,
           {"free_mib": round(free_bytes / _MIB, 0), "total_mib": round(total_bytes / _MIB, 0)})

    torch.manual_seed(0)
    size = args.size
    cpu_a = torch.randn(size, size)
    cpu_b = torch.randn(size, size)
    reference = cpu_a @ cpu_b

    gpu_a = cpu_a.to(device)
    gpu_b = cpu_b.to(device)
    gpu_result = (gpu_a @ gpu_b).cpu()
    max_error = float((gpu_result - reference).abs().max())
    record("fp32_matmul_matches_cpu", torch.allclose(gpu_result, reference, atol=1e-3, rtol=1e-3),
           {"size": size, "max_abs_error": max_error})
    payload["fp32_matmul_max_abs_error"] = max_error

    bf16_supported = bool(torch.cuda.is_bf16_supported())
    record("bf16_supported", bf16_supported, bf16_supported)
    if bf16_supported:
        a16 = gpu_a.to(torch.bfloat16)
        b16 = gpu_b.to(torch.bfloat16)
        out16 = (a16 @ b16).to(torch.float32).cpu()
        rel = float(((out16 - reference).abs() / reference.abs().clamp_min(1e-3)).mean())
        record("bf16_matmul_matches_fp32", rel < 0.02, {"mean_relative_error": rel})
        payload["bf16_mean_relative_error"] = rel

    # Autograd: a parameter must actually move after one optimisation step.
    parameter = torch.randn(256, 256, device=device, requires_grad=True)
    optimiser = torch.optim.Adam([parameter], lr=1e-3)
    before = parameter.detach().clone()
    optimiser.zero_grad(set_to_none=True)
    loss = (parameter @ parameter).pow(2).mean()
    loss.backward()
    grad_norm = float(parameter.grad.norm())
    optimiser.step()
    moved = float((parameter.detach() - before).norm())
    record("autograd_and_optimizer", grad_norm > 0 and moved > 0,
           {"loss": float(loss), "grad_norm": grad_norm, "parameter_delta": moved})

    # Throughput: synchronised, repeated, median.
    times: list[float] = []
    torch.cuda.synchronize()
    for _ in range(args.iters):
        started = time.perf_counter()
        _ = gpu_a @ gpu_b
        torch.cuda.synchronize()
        times.append(time.perf_counter() - started)
    median = statistics.median(times)
    tflops = (2 * size ** 3) / median / 1e12
    record("fp32_matmul_throughput", median > 0, {"median_s": round(median, 6), "tflops": round(tflops, 3)})
    payload.update({"matmul_median_s": round(median, 6), "matmul_tflops": round(tflops, 3)})

    peak = torch.cuda.max_memory_allocated(0)
    payload["peak_allocated_mib"] = round(peak / _MIB, 1)
    payload["verdict"] = "PASSED" if all(check["passed"] for check in checks) else "FAILED"
    print(f"\nverdict: {payload['verdict']}")
    _write(args.out, payload)
    return 0 if payload["verdict"] == "PASSED" else 1


def _write(out: str | None, payload: dict[str, Any]) -> None:
    if not out:
        return
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"written -> {path}")


if __name__ == "__main__":
    raise SystemExit(main())
