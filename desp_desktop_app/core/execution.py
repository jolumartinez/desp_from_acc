from __future__ import annotations

import multiprocessing as mp
import os
import queue
import time
import traceback
from collections.abc import Callable
from typing import Any

from .catalog import METHOD_BY_ID
from .engine import run_method_traced
from .models import MethodResult, PartialMethodResult, ProcessStep, SignalRecord


DEFAULT_METHOD_TIMEOUT_S = 15.0 * 60.0
POLL_INTERVAL_S = 0.20


def _method_process_entry(
    output_queue: Any,
    method_id: str,
    record: SignalRecord,
    parameters: dict[str, Any],
) -> None:
    try:
        result = run_method_traced(
            method_id,
            record,
            parameters,
            step_callback=lambda step: output_queue.put(("step", step)),
        )
        output_queue.put(("result", result))
    except BaseException:  # noqa: BLE001
        output_queue.put(("error", traceback.format_exc()))


def _partial_result(
    method_id: str,
    steps: list[ProcessStep],
    message: str,
    elapsed_s: float,
) -> PartialMethodResult:
    spec = METHOD_BY_ID.get(method_id)
    return PartialMethodResult(
        method_id=method_id,
        method_name=spec.name if spec is not None else method_id,
        steps=steps.copy(),
        failure_message=message,
        elapsed_s=elapsed_s,
    )


def run_method_isolated(
    method_id: str,
    record: SignalRecord,
    parameters: dict[str, Any],
    *,
    on_step: Callable[[ProcessStep], None] | None = None,
    on_heartbeat: Callable[[float], None] | None = None,
    cancel_requested: Callable[[], bool] | None = None,
    timeout_s: float = DEFAULT_METHOD_TIMEOUT_S,
) -> MethodResult | PartialMethodResult:
    """Execute one method in a disposable process while streaming completed steps."""
    numeric_threads = os.environ.get("DESP_NUMERIC_THREADS", "1")
    if not numeric_threads.isdigit() or int(numeric_threads) < 1:
        numeric_threads = "1"
    for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[variable] = numeric_threads

    if cancel_requested is not None and cancel_requested():
        return _partial_result(method_id, [], "Ejecución cancelada por el usuario.", 0.0)

    context = mp.get_context("spawn")
    output_queue = context.Queue()
    process = context.Process(
        target=_method_process_entry,
        args=(output_queue, method_id, record, dict(parameters)),
        name=f"desp-{method_id}",
        daemon=True,
    )
    steps: list[ProcessStep] = []
    started = time.monotonic()
    last_heartbeat = -1.0
    process.start()

    try:
        while True:
            elapsed = time.monotonic() - started
            if cancel_requested is not None and cancel_requested():
                return _partial_result(
                    method_id,
                    steps,
                    "Ejecución cancelada por el usuario.",
                    elapsed,
                )
            if timeout_s > 0.0 and elapsed > timeout_s:
                return _partial_result(
                    method_id,
                    steps,
                    f"Tiempo máximo de cálculo excedido ({timeout_s:.0f} s).",
                    elapsed,
                )
            if on_heartbeat is not None and elapsed - last_heartbeat >= 1.0:
                on_heartbeat(elapsed)
                last_heartbeat = elapsed

            try:
                message_type, payload = output_queue.get(timeout=POLL_INTERVAL_S)
            except queue.Empty:
                if process.is_alive():
                    continue
                try:
                    message_type, payload = output_queue.get(timeout=0.5)
                except queue.Empty:
                    return _partial_result(
                        method_id,
                        steps,
                        f"El proceso de cálculo terminó inesperadamente (código {process.exitcode}).",
                        elapsed,
                    )

            if message_type == "step":
                steps.append(payload)
                if on_step is not None:
                    on_step(payload)
            elif message_type == "result":
                return payload
            elif message_type == "error":
                first_line = str(payload).strip().splitlines()[-1]
                return _partial_result(method_id, steps, first_line, elapsed)
    finally:
        if process.is_alive():
            process.terminate()
        process.join(timeout=2.0)
        if process.is_alive() and hasattr(process, "kill"):
            process.kill()
            process.join(timeout=1.0)
        output_queue.close()
        output_queue.cancel_join_thread()
