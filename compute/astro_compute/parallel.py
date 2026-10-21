"""Independent pieces of one request in forked worker processes (the lead's latency plan,
step 2): a year list's scans and its days. Lambda has no /dev/shm, so each worker sends its
results back through a Pipe, and Swiss Ephemeris is closed before the fork so no two processes
share an open ephemeris file. One worker, or one piece, runs in this process. The pieces and
their order are the same either way, so the answers are byte for byte the same."""

import multiprocessing
import os
import traceback

import swisseph as swe


def workers() -> int:
    """ASTRO_WORKERS if set, else the CPUs this process may use (6 on a 10240 MB Lambda)."""
    return int(os.environ.get("ASTRO_WORKERS") or len(os.sched_getaffinity(0)))


def _ephemeris() -> None:
    """swe.close() forgets the ephemeris path: set it again, as jyotisha.ephemeris does."""
    path = os.environ.get("SE_EPHE_PATH")
    if path:
        swe.set_ephe_path(os.path.expanduser(path))


def _work(calls: list, k: int, n: int, send) -> None:
    _ephemeris()
    try:
        send.send(("ok", [calls[i]() for i in range(k, len(calls), n)]))
    except BaseException:  # noqa: BLE001 - the parent raises it
        send.send(("error", traceback.format_exc()))
    send.close()


def run(calls: list) -> list:
    """[call() for call in calls], call i on worker i % n; the results in call order."""
    n = min(workers(), len(calls))
    if n <= 1:
        return [call() for call in calls]
    swe.close()
    ctx = multiprocessing.get_context("fork")
    jobs = []
    for k in range(n):
        recv, send = ctx.Pipe(duplex=False)
        proc = ctx.Process(target=_work, args=(calls, k, n, send), daemon=True)
        proc.start()
        send.close()
        jobs.append((proc, recv))
    _ephemeris()
    out: list = [None] * len(calls)
    failure = None
    for k, (proc, recv) in enumerate(jobs):
        try:
            status, value = recv.recv()
        except EOFError:
            status, value = "error", f"worker {k} exited without a result"
        recv.close()
        proc.join()
        if status == "ok":
            out[k::n] = value
        else:
            failure = failure or value
    if failure:
        raise RuntimeError(f"a worker failed:\n{failure}")
    return out
