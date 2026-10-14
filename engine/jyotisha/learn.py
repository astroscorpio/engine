"""A model that can learn from events as they arrive -- and can tell you when
it has learned nothing.

The framing: chop time into fixed windows; for each window and life domain the
outcome is binary, did a notable event occur.  That turns a vague forecast into
a probability with a proper score attached.

Three properties are non-negotiable, because without them a model like this
always looks good:

* **A base-rate opponent.**  Every score is reported as skill *against* a model
  that knows only how often things happen.  Beating nothing is not a result.
* **Prequential evaluation.**  Fit on the past, predict the next window, score
  it, then move on.  No window is ever scored by a model that has seen it.
* **Strong shrinkage.**  With 29 techniques and a couple of dozen events, an
  unregularised fit memorises instantly.  The prior is tight and centred on
  zero, so a technique has to earn its weight.

If the techniques are noise, the posterior stays at zero, the predictions stay
at the base rate, and the skill score stays at or below zero.  That is the
system working, not failing.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

import numpy as np

from .chart import Chart
from .ephemeris import TimeZone, parse, to_datetime
from .subjects import Subject

WINDOW_DAYS = 14


def windows(
    start_jd: float,
    end_jd: float,
    days: int = WINDOW_DAYS,
    *,
    timezone: TimeZone | None = None,
):
    """Complete, non-overrunning half-open windows in ``[start, end]``."""
    if days <= 0:
        raise ValueError("window length must be positive")
    if timezone is not None:
        start = to_datetime(start_jd, timezone)
        result = []
        index = 0
        while True:
            a = parse((start + dt.timedelta(days=index * days)).isoformat())
            b = parse((start + dt.timedelta(days=(index + 1) * days)).isoformat())
            if b > end_jd + 1e-9:
                break
            result.append((a, b))
            index += 1
        return result
    n = max(0, int(math.floor((end_jd - start_jd) / days + 1e-12)))
    return [(start_jd + i * days, start_jd + (i + 1) * days) for i in range(n)]


def future_windows(
    start_jd: float,
    count: int,
    days: int = WINDOW_DAYS,
    *,
    timezone: TimeZone | None = None,
) -> list[tuple[float, float]]:
    if count < 1:
        raise ValueError("future window count must be at least one")
    if timezone is not None:
        start = to_datetime(start_jd, timezone)
        boundaries = [
            parse((start + dt.timedelta(days=i * days)).isoformat()) for i in range(count + 1)
        ]
        return list(zip(boundaries[:-1], boundaries[1:], strict=True))
    return [(start_jd + i * days, start_jd + (i + 1) * days) for i in range(count)]


def _event_jd(subject: Subject, event) -> float:
    zone = event.tz if event.tz is not None else subject.birth_zone
    stamp = event.date
    if event.time and len(event.date) == 10:
        stamp = f"{event.date} {event.time}"
    return parse(stamp, zone)


def label(
    subject: Subject,
    wins,
    domain: str,
    *,
    polarity: int | None = None,
    min_magnitude: int = 2,
    allowed_confidence: tuple[str, ...] = ("day", "week"),
) -> np.ndarray:
    """1 if a *point* event in this domain falls in the window.

    Sustained states are deliberately excluded: 'topped the class for three
    years' would mark eighty windows positive and swamp everything.  They are
    context, not events.
    """
    y = np.zeros(len(wins), dtype=float)
    for e in subject.events:
        if e.is_interval or domain not in e.domains:
            continue
        if getattr(e, "kind", "event") != "event":
            continue  # notifications and markers are not outcomes
        if getattr(e, "contaminated", ""):
            continue
        if e.confidence not in allowed_confidence or len(e.date) != 10:
            continue
        if e.magnitude < min_magnitude:
            continue
        if polarity is not None and e.polarity != polarity:
            continue
        jd = _event_jd(subject, e)
        for i, (a, b) in enumerate(wins):
            if a <= jd < b:
                y[i] = 1.0
    return y


def featurize(
    chart: Chart,
    wins,
    hypotheses,
    event_proto,
    *,
    timezone: TimeZone | None = None,
) -> np.ndarray:
    """Raw technique aggregates. Scaling belongs to the fitted pipeline."""
    X = np.zeros((len(wins), 2 * len(hypotheses)))
    for i, (a, b) in enumerate(wins):
        if timezone is None:
            samples = np.arange(a, b, 1.0)
        else:
            first = to_datetime(a, timezone).date()
            last = (to_datetime(b, timezone) - dt.timedelta(microseconds=1)).date()
            dates = [first + dt.timedelta(days=offset) for offset in range((last - first).days + 1)]
            samples = np.asarray(
                [parse(date.isoformat(), timezone) for date in dates],
                dtype=float,
            )
        for j, h in enumerate(hypotheses):
            vals = np.array([h.score(chart, day, event_proto) for day in samples])
            X[i, 2 * j] = vals.mean()
            X[i, 2 * j + 1] = vals.max()
    return X


@dataclass
class Standardizer:
    mean: np.ndarray | None = None
    scale: np.ndarray | None = None

    def fit(self, X: np.ndarray) -> Standardizer:
        if X.ndim != 2 or len(X) == 0:
            raise ValueError("cannot fit a standardizer to an empty matrix")
        self.mean = X.mean(axis=0)
        self.scale = X.std(axis=0)
        self.scale[self.scale < 1e-9] = 1.0
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        if self.mean is None or self.scale is None:
            raise RuntimeError("standardizer has not been fitted")
        return (X - self.mean) / self.scale

    def fit_transform(self, X: np.ndarray) -> np.ndarray:
        return self.fit(X).transform(X)


def calendar_features(wins, timezone: TimeZone) -> np.ndarray:
    """Non-astrological calendar opponent: season, weekday, and trend."""
    if not wins:
        return np.empty((0, 5))
    rows = []
    for a, b in wins:
        mid = (a + b) / 2
        civil = to_datetime(mid, timezone)
        year_phase = 2 * math.pi * (civil.timetuple().tm_yday - 1) / 365.2425
        week_phase = 2 * math.pi * civil.weekday() / 7
        rows.append(
            [
                math.sin(year_phase),
                math.cos(year_phase),
                math.sin(week_phase),
                math.cos(week_phase),
                (mid - 2451545.0) / 365.2425,
            ]
        )
    return np.asarray(rows, dtype=float)


@dataclass
class BayesLogistic:
    """Logistic regression, MAP fit with a Gaussian prior, Laplace posterior.

    tau is the prior sd on each weight.  Keep it small: it is the only thing
    standing between twenty events and a perfectly fitted fantasy.
    """

    tau: float = 0.25
    w: np.ndarray | None = None
    cov: np.ndarray | None = None

    def fit(self, X: np.ndarray, y: np.ndarray, iters: int = 60):
        n, p = X.shape
        Xb = np.hstack([np.ones((n, 1)), X])
        w = np.zeros(p + 1)
        # the intercept is the base rate and must not be shrunk
        prior = np.full(p + 1, 1.0 / self.tau**2)
        prior[0] = 1e-6
        for _ in range(iters):
            eta = np.clip(Xb @ w, -30, 30)
            mu = 1 / (1 + np.exp(-eta))
            s = np.maximum(mu * (1 - mu), 1e-6)
            g = Xb.T @ (y - mu) - prior * w
            H = (Xb * s[:, None]).T @ Xb + np.diag(prior)
            step = np.linalg.solve(H, g)
            w += step
            if np.max(np.abs(step)) < 1e-8:
                break
        self.w, self.cov = w, np.linalg.inv(H)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Posterior-mean probability, widened by parameter uncertainty."""
        Xb = np.hstack([np.ones((X.shape[0], 1)), X])
        mu = Xb @ self.w
        var = np.einsum("ij,jk,ik->i", Xb, self.cov, Xb)
        kappa = 1 / np.sqrt(1 + math.pi * var / 8)  # probit approximation
        return 1 / (1 + np.exp(-np.clip(kappa * mu, -30, 30)))

    def weight_table(self, names: list[str], top: int = 12) -> str:
        sd = np.sqrt(np.diag(self.cov))
        rows = sorted(range(1, len(self.w)), key=lambda i: -abs(self.w[i] / sd[i]))
        out = [f"{'technique':52s}{'weight':>9s}{'sd':>8s}{'w/sd':>7s}"]
        for i in rows[:top]:
            out.append(
                f"{names[i - 1][:51]:52s}{self.w[i]:9.3f}{sd[i]:8.3f}{self.w[i] / sd[i]:7.2f}"
            )
        moved = int((np.abs(self.w[1:] / sd[1:]) > 2).sum())
        out.append(f"  weights more than 2 sd from zero: {moved} of {len(self.w) - 1}")
        return "\n".join(out)


def log_score(y: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _log_loss(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def hac_one_sided(loss_gain: np.ndarray) -> tuple[float, float, float]:
    """Mean gain, HAC z score, and one-sided asymptotic p-value."""
    n = len(loss_gain)
    if n == 0:
        return 0.0, 0.0, 1.0
    if n < 3:
        return float(loss_gain.mean()), 0.0, 1.0
    gain = float(loss_gain.mean())
    dev = loss_gain - gain
    lag_max = max(1, min(n - 1, int(round(n ** (1 / 3)))))
    long_run_variance = float(dev @ dev / n)
    for lag in range(1, lag_max + 1):
        covariance = float(dev[:-lag] @ dev[lag:] / n)
        long_run_variance += 2 * (1 - lag / (lag_max + 1)) * covariance
    standard_error = math.sqrt(max(long_run_variance, 0.0) / n)
    if standard_error < 1e-12:
        return gain, 0.0, 1.0
    z_score = gain / standard_error
    p_value = 0.5 * math.erfc(z_score / math.sqrt(2))
    return gain, z_score, p_value


def brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((y - p) ** 2))


def prequential(
    X: np.ndarray,
    y: np.ndarray,
    burn_in: int = 40,
    tau: float = 0.25,
    calendar_X: np.ndarray | None = None,
) -> dict:
    """Walk forward: fit on everything before window t, predict window t.

    This is the only score that means anything.  Nothing is ever predicted by
    a model that has seen it.
    """
    if len(X) != len(y):
        raise ValueError("X and y must have the same number of rows")
    if calendar_X is not None and len(calendar_X) != len(y):
        raise ValueError("calendar_X and y must have the same number of rows")
    preds, calendar_preds, constant_preds, actual = [], [], [], []
    for t in range(burn_in, len(y)):
        past_y = y[:t]
        if past_y.sum() < 2:
            continue
        scaler = Standardizer().fit(X[:t])
        past_X = scaler.transform(X[:t])
        next_X = scaler.transform(X[t : t + 1])
        if calendar_X is not None:
            c_scaler = Standardizer().fit(calendar_X[:t])
            past_C = c_scaler.transform(calendar_X[:t])
            next_C = c_scaler.transform(calendar_X[t : t + 1])
            calendar_model = BayesLogistic(tau=0.5).fit(past_C, past_y)
            calendar_pred = float(calendar_model.predict(next_C)[0])
            full_past = np.hstack([past_C, past_X])
            full_next = np.hstack([next_C, next_X])
        else:
            calendar_pred = float((past_y.sum() + 0.5) / (len(past_y) + 1.0))
            full_past, full_next = past_X, next_X
        model = BayesLogistic(tau=tau).fit(full_past, past_y)
        preds.append(float(model.predict(full_next)[0]))
        calendar_preds.append(calendar_pred)
        constant_preds.append(float((past_y.sum() + 0.5) / (len(past_y) + 1.0)))
        actual.append(float(y[t]))
    y_a = np.array(actual)
    p_m = np.array(preds)
    p_c = np.array(calendar_preds)
    p_b = np.array(constant_preds)
    if not len(y_a):
        return {
            "n_scored": 0,
            "n_events": 0,
            "log_model": float("nan"),
            "log_calendar": float("nan"),
            "log_base": float("nan"),
            "skill": 0.0,
            "skill_constant": 0.0,
            "mean_log_loss_gain": 0.0,
            "hac_z": 0.0,
            "skill_p": 1.0,
            "brier_model": float("nan"),
            "brier_calendar": float("nan"),
            "brier_base": float("nan"),
            "p": p_m,
            "p_calendar": p_c,
            "p_base": p_b,
            "y": y_a,
        }
    ls_m, ls_c, ls_b = (log_score(y_a, p_m), log_score(y_a, p_c), log_score(y_a, p_b))
    gain, hac_z, skill_p = hac_one_sided(_log_loss(y_a, p_c) - _log_loss(y_a, p_m))
    return {
        "n_scored": len(y_a),
        "n_events": int(y_a.sum()),
        "log_model": ls_m,
        "log_calendar": ls_c,
        "log_base": ls_b,
        "skill": 1 - ls_m / ls_c if ls_c > 0 else 0.0,
        "skill_constant": 1 - ls_m / ls_b if ls_b > 0 else 0.0,
        "mean_log_loss_gain": gain,
        "hac_z": hac_z,
        "skill_p": skill_p,
        "brier_model": brier(y_a, p_m),
        "brier_calendar": brier(y_a, p_c),
        "brier_base": brier(y_a, p_b),
        "p": p_m,
        "p_calendar": p_c,
        "p_base": p_b,
        "y": y_a,
    }


def calibration(y: np.ndarray, p: np.ndarray, bins: int = 5) -> str:
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    edges[-1] += 1e-9
    out = [f"{'predicted band':22s}{'n':>6s}{'mean predicted':>16s}{'actually happened':>19s}"]
    for i in range(bins):
        m = (p >= edges[i]) & (p < edges[i + 1])
        if not m.any():
            continue
        out.append(
            f"{f'{edges[i]:.3f} - {edges[i + 1]:.3f}':22s}"
            f"{int(m.sum()):6d}{p[m].mean():16.3f}{y[m].mean():19.3f}"
        )
    return "\n".join(out)


# Minimum windows and events before a skill claim is allowed to stand.
# A walk-forward run that scores two windows containing one event will happily
# report skill = +0.66.  That is noise with a verdict attached, and it is
# exactly the failure this module was written to prevent -- so the guard is
# part of the report, not a caller's responsibility.
MIN_SCORED = 40
MIN_EVENTS = 5


def report(res: dict) -> str:
    if res["n_scored"] < MIN_SCORED or res["n_events"] < MIN_EVENTS:
        verdict = (
            f"UNDERPOWERED -- {res['n_scored']} windows and "
            f"{res['n_events']} events is not enough to claim anything "
            f"(need {MIN_SCORED} and {MIN_EVENTS}). The skill number "
            f"below is noise; ignore its sign."
        )
    elif res["skill"] > 0 and res["skill_p"] < 0.05:
        verdict = (
            "RETROSPECTIVE SIGNAL -- lower prequential loss than the calendar "
            "opponent; requires a sealed prospective trial"
        )
    else:
        verdict = "NO DEMONSTRATED SKILL -- does not reliably beat the calendar opponent"
    return "\n".join(
        [
            f"  windows scored          {res['n_scored']}",
            f"  events among them       {res['n_events']}",
            f"  log score, model        {res['log_model']:.4f}",
            f"  log score, calendar     {res['log_calendar']:.4f}",
            f"  log score, constant     {res['log_base']:.4f}",
            f"  skill vs calendar       {res['skill']:+.4f}",
            f"  skill vs constant       {res['skill_constant']:+.4f}",
            f"  HAC one-sided p         {res['skill_p']:.4f}",
            f"  Brier model/calendar    {res['brier_model']:.4f} / {res['brier_calendar']:.4f}",
            "",
            f"  VERDICT: {verdict}",
        ]
    )
