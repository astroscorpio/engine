"""Command line front end.  No GUI, no state, everything to stdout."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import inspect as pyinspect
import json
import sys
from dataclasses import asdict

import numpy as np

from . import ashtakavarga as av
from . import backtest as B
from . import dashas as D
from . import hypotheses as H
from .context import ObserverContext
from .ephemeris import (
    AYANAMSAS,
    GRAHAS,
    SIGNS,
    fmt,
    ingress_dates,
    now,
    parse,
    positions,
    station_dates,
    to_datetime,
)
from .subjects import DOMAINS, SUBJECTS
from .vargas import VARGA_NAMES, VARGA_SIGNIFIES, varga

FORECAST_MODEL = "calendar+bayeslogistic-tau0.25-v3"


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def _nonnegative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return parsed


def _nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be a nonnegative integer")
    return parsed


def _context(sub, args) -> ObserverContext:
    base = sub.observer_context
    lat = getattr(args, "lat", None)
    lon = getattr(args, "lon", None)
    if (lat is None) != (lon is None):
        raise ValueError("--lat and --lon must be supplied together")
    return base.overridden(
        lat=lat,
        lon=lon,
        timezone=getattr(args, "timezone", None),
        place=getattr(args, "place", None),
    )


def _current_stamp(context: ObserverContext) -> str:
    return now(context.timezone).isoformat(timespec="seconds")


def _date_or_now(value: str | None, context: ObserverContext) -> float:
    return parse(value, context.timezone) if value else parse(_current_stamp(context))


def _today(context: ObserverContext) -> str:
    return now(context.timezone).date().isoformat()


def _record_exposure(jd: float, context: ObserverContext, command: str) -> None:
    """Mark the civil date whose astrological information was displayed.

    Future dates matter too: seeing tomorrow's forecast before tomorrow's
    rating would break the blind daily protocol just as surely as seeing it
    on the day itself.
    """
    civil_date = to_datetime(jd, context.timezone).date().isoformat()
    from . import daily

    daily.record_exposure(civil_date, command)


def _record_exposure_window(
    start_jd: float,
    end_jd: float,
    context: ObserverContext,
    command: str,
) -> None:
    """Mark every local civil date touched by a half-open forecast window."""
    if end_jd <= start_jd:
        raise ValueError("exposure window end must follow start")
    from . import daily

    first = to_datetime(start_jd, context.timezone).date()
    last = (to_datetime(end_jd, context.timezone) - dt.timedelta(microseconds=1)).date()
    date = first
    while date <= last:
        daily.record_exposure(date.isoformat(), command)
        date += dt.timedelta(days=1)


def _civil_day_jd(start: str, offset: int, context: ObserverContext) -> float:
    """Advance by local civil days while preserving the requested wall time."""
    base = to_datetime(parse(start, context.timezone), context.timezone)
    date = base.date() + dt.timedelta(days=offset)
    wall_time = base.time().replace(tzinfo=None).isoformat()
    return parse(f"{date.isoformat()}T{wall_time}", context.timezone)


def _emit(value, output_format: str = "human") -> None:
    if output_format == "human":
        print(
            value
            if isinstance(value, str)
            else json.dumps(value, indent=2, ensure_ascii=False, default=str)
        )
    elif output_format == "json":
        print(json.dumps(value, indent=2, ensure_ascii=False, default=str))
    elif output_format == "jsonl":
        rows = value if isinstance(value, list) else [value]
        for row in rows:
            print(json.dumps(row, ensure_ascii=False, default=str))
    elif output_format == "csv":
        rows = value if isinstance(value, list) else [value]
        if not rows or not all(isinstance(row, dict) for row in rows):
            raise ValueError("CSV output requires a list of flat records")
        if any(isinstance(item, (dict, list, tuple, set)) for row in rows for item in row.values()):
            raise ValueError("CSV output does not support nested values")
        fields = sorted({key for row in rows for key in row})
        writer = csv.DictWriter(sys.stdout, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    else:
        raise ValueError(f"unsupported output format {output_format!r}")


def cmd_chart(sub, args):
    c = sub.chart(ayanamsa=args.ayanamsa, node=args.node)
    print(f"=== {sub.name} — D1 ({args.ayanamsa}) ===\n")
    print(c.table())
    print()
    print(c.grid())
    if args.vargas:
        divisions = [int(value.strip()) for value in args.vargas.split(",") if value.strip()]
        invalid = [division for division in divisions if division < 1]
        if invalid:
            raise ValueError("varga divisions must be positive integers")
        print("\n=== DIVISIONALS (sign) ===")
        head = f"{'':10s}" + "".join(f"{'D' + str(d):>7s}" for d in divisions)
        print(head)
        for name in ["Ascendant", *GRAHAS]:
            body = c.asc if name == "Ascendant" else c.grahas[name]
            cells = "".join(
                f"{SIGNS[int(varga(body.longitude, d) // 30)][:3]:>7s}" for d in divisions
            )
            print(f"{name:10s}{cells}")
        print()
        for d in divisions:
            print(f"  D{d:<3d} {VARGA_NAMES.get(d, '?'):18s} {VARGA_SIGNIFIES.get(d, '')}")


def cmd_av(sub, args):
    c = sub.chart(ayanamsa=args.ayanamsa, node=args.node)
    print(f"=== ASHTAKAVARGA — {sub.name} ===\n")
    print(av.report(c))


def cmd_dasha(sub, args):
    c = sub.chart(ayanamsa=args.ayanamsa, node=args.node)
    context = _context(sub, args)
    jd = _date_or_now(args.on, context)
    label = fmt(jd, context.timezone, True)
    for kind, tree in (
        ("Vimshottari", D.vimshottari(c)),
        ("Yogini", D.yogini(c)),
        ("Ashtottari", D.ashtottari(c)),
        ("Chara (A)", D.chara(c, convention="A")),
        ("Chara (B)", D.chara(c, convention="B")),
    ):
        print(f"\n=== {kind} on {label} ===")
        if kind == "Ashtottari":
            print(f"  applicability: {'holds' if D.ashtottari_applies(c) else 'does not hold'}")
        for p in D.active(tree, jd):
            print(
                f"  L{p.level} {p.lord:18s} "
                f"{fmt(p.start, context.timezone, True)} -> "
                f"{fmt(p.end, context.timezone, True)}"
            )
    _record_exposure(jd, context, "dasha")


def cmd_ladder(sub, args):
    """Sub-periods at one level, so a window can be read off directly."""
    c = sub.chart(ayanamsa=args.ayanamsa, node=args.node)
    tree = D.vimshottari(c)
    context = _context(sub, args)
    jd = _date_or_now(args.on, context)
    for level in range(2, args.level + 1):
        rows = D.siblings(tree, jd, level)
        chain = D.active(tree, jd)
        prefix = "-".join(p.lord for p in chain[: level - 1])
        print(f"\n=== level {level}: {prefix}-* ===")
        for p in rows:
            mark = "  <== now" if p.at(jd) else ""
            print(
                f"  {prefix}-{p.lord:9s} "
                f"{fmt(p.start, context.timezone, True)} -> "
                f"{fmt(p.end, context.timezone, True)}{mark}"
            )
    _record_exposure(jd, context, "ladder")


def cmd_transit(sub, args):
    c = sub.chart(ayanamsa=args.ayanamsa, node=args.node)
    context = _context(sub, args)
    jd = _date_or_now(args.on, context)
    moving = positions(jd, args.ayanamsa, args.node)
    sav = av.sarva(av.bhinna(c))
    print(
        f"=== TRANSITS {fmt(jd, context.timezone, True)} — "
        f"{D.chain_label(D.vimshottari(c), jd)} ===\n"
    )
    print(f"{'':10s}{'position':14s}{'ho':>3s}{'SAV':>5s}{'kaksh':>7s}{'lord':>9s}{'state':>9s}")
    for name in GRAHAS:
        p = moving[name]
        house = (p.sign - c.asc.sign) % 12 + 1
        if name in av.BAV_RULES:
            k = av.kakshya_transit(c, moving, name)
            extra = (
                f"{k['kakshya']:7d}{k['kakshya_lord']:>9s}"
                f"{'active' if k['active'] else 'inert':>9s}"
            )
        else:
            extra = " " * 25
        print(f"{name:10s}{p!s:14s}{house:3d}{sav[p.sign]:5d}{extra}")
    _record_exposure(jd, context, "transit")


def cmd_events(sub, args):
    """Slow-planet stations and ingresses across a span."""
    context = _context(sub, args)
    start = args.start or _today(context)
    if args.end:
        end = args.end
    else:
        end_date = now(context.timezone).date() + dt.timedelta(days=548)
        end = end_date.isoformat()
    lo, hi = parse(start, context.timezone), parse(end, context.timezone)
    if hi <= lo:
        raise ValueError("--end must follow --start")
    rows = []
    for body in ["Mercury", "Venus", "Mars", "Jupiter", "Saturn"]:
        for s in station_dates(body, lo, hi, args.ayanamsa):
            rows.append(
                (
                    s["jd"],
                    f"{body} turns {s['direction']} at "
                    f"{SIGNS[int(s['longitude'] // 30)]} "
                    f"{s['longitude'] % 30:.0f}°",
                )
            )
    for body in ["Jupiter", "Saturn", "Rahu", "Ketu", "Mars"]:
        for g in ingress_dates(
            body,
            lo,
            hi,
            args.ayanamsa,
            node=args.node,
        ):
            rows.append((g["jd"], f"{body} enters {SIGNS[g['sign']]}"))
    c = sub.chart(ayanamsa=args.ayanamsa, node=args.node)
    tree = D.vimshottari(c)
    for jd_, text in sorted(rows):
        print(f"  {fmt(jd_, context.timezone, True):19s} {text:44s} [{D.chain_label(tree, jd_)}]")


def cmd_backtest(sub, args):
    options = {
        "n_null": args.nulls,
        "ayanamsa": args.ayanamsa,
        "node": args.node,
        "null_mode": args.null_mode,
        "seed": args.seed,
        "gate_precision": not args.no_precision_gate,
        "workers": args.workers,
    }
    if args.format == "human":
        print(f"=== BACKTEST — {sub.name}, {len(sub.events)} events, {args.nulls} null draws ===\n")
        print(B.family_report(sub, H.LIBRARY, **options))
    else:
        results = B.run(sub, H.LIBRARY, **options)
        _emit(
            [
                {
                    "hypothesis": r.hypothesis,
                    "n_events": r.n_events,
                    "empirical_p": r.empirical_p,
                    "fwer_p": r.fwer_p,
                    "bh_q": r.bh_q,
                    "aggregate_percentile": r.aggregate_percentile,
                    "degenerate_events": r.degenerate,
                    "verdict": r.verdict,
                    "per_event": r.per_event,
                }
                for r in results
            ],
            args.format,
        )


def cmd_ayanamsa(sub, args):
    keep = {
        "dasha lord rules the domain house",
        "slow transit on/aspecting domain",
        "transit over natal dasha lord",
        "kakshya vedha (Sat/Jup inert kakshya)",
        "transit Moon trigger",
        "near a planetary station",
        "CONTROL: pseudo-random noise",
    }
    subset = [h for h in H.LIBRARY if h.name in keep]
    print(B.compare_ayanamsas(sub, subset, n_null=args.nulls, node=args.node))


def cmd_rectify(sub, args):
    """Sweep the birth time and score each candidate against the events.

    With a handful of events this overfits freely -- treat the output as a
    shortlist to check against independent evidence, never as an answer.
    """
    print(f"=== RECTIFICATION SWEEP — ±{args.span} min, step {args.step} ===")
    print(f"    {len(sub.events)} events. Overfitting risk is high below ~15 events.\n")
    scans = []
    steps = int(args.span / args.step)
    for i in range(-steps, steps + 1):
        candidate = sub.shifted(i * args.step)
        results = B.run(
            candidate,
            [h for h in H.LIBRARY if not h.name.startswith("CONTROL")],
            n_null=args.nulls,
            ayanamsa=args.ayanamsa,
            node=args.node,
        )
        asc = candidate.chart(ayanamsa=args.ayanamsa, node=args.node).asc
        informative = [r for r in results if r.n_events and r.degenerate < r.n_events]
        scans.append((i * args.step, asc, informative))
    joint = [result for _, _, results in scans for result in results]
    if joint:
        B.joint_fwer(joint)
    rows = []
    for offset, asc, results in scans:
        best = min(results, key=lambda result: result.fwer_p, default=None)
        rows.append(
            (
                offset,
                asc,
                best.fwer_p if best else 1.0,
                best.hypothesis if best else "no informative technique",
            )
        )
    for offset, asc, p, who in rows:
        print(f"  {offset:+6.1f} min  asc {asc!s:13s} joint FWER p={p:.3f}  {who[:36]}")
    print("\n  Birth-time and technique searches are corrected jointly; this is not validation.")


def cmd_strength(sub, args):
    from . import strength as S

    c = sub.chart(ayanamsa=args.ayanamsa, node=args.node)
    print(f"=== SHADBALA — {sub.name} ===\n")
    print(S.report(c))
    print("\n=== BHAVA BALA ===")
    bb = S.bhava_bala(c)
    print(f"{'house':>6s}{'adhipati':>10s}{'drishti':>9s}{'occup':>8s}{'dig':>7s}{'total':>9s}")
    for h in range(1, 13):
        b = bb[h]
        print(
            f"{h:6d}{b['adhipati']:10.1f}{b['drishti']:9.1f}"
            f"{b['occupants']:8.1f}{b['dig']:7.1f}{b['total']:9.1f}"
        )


def cmd_states(sub, args):
    from . import states as St

    print(St.report(sub.chart(ayanamsa=args.ayanamsa, node=args.node)))


def cmd_points(sub, args):
    from . import upagraha as U

    print(U.report(sub.chart(ayanamsa=args.ayanamsa, node=args.node)))


def cmd_jaimini(sub, args):
    from . import jaimini as J

    print(J.report(sub.chart(ayanamsa=args.ayanamsa, node=args.node)))


def cmd_yogas(sub, args):
    from . import yogas as Y

    print(Y.report(sub.chart(ayanamsa=args.ayanamsa, node=args.node)))


def cmd_muhurta(sub, args):
    from . import muhurta as Mu

    context = _context(sub, args)
    chart = sub.chart(ayanamsa=args.ayanamsa, node=args.node)
    if args.find:
        _muhurta_find(Mu, context, chart, args)
        return
    start = _date_or_now(args.start, context)
    natal_moon = chart.grahas["Moon"]
    for i in range(args.days):
        jd = _civil_day_jd(args.start, i, context) if args.start else start + i
        day = Mu.day(jd, context.lat, context.lon, args.ayanamsa)
        _record_exposure_window(day.sunrise, day.next_sunrise, context, "muhurta")
        print(Mu.report(day, context.timezone, natal_moon, args.ayanamsa))
        print()


def _muhurta_find(Mu, context, chart, args) -> None:
    profile = Mu.PROFILES.get(args.find)
    if profile is None:
        raise ValueError(f"unknown act {args.find!r}; choose from {', '.join(Mu.PROFILES)}")
    tz = context.timezone
    toward = Mu.resolve_direction(args.toward)
    if profile.travel and toward is None:
        raise ValueError("--find travel needs --toward, the destination's direction")
    at = None
    if args.at is not None:
        at = _date_or_now(None if args.at == "now" else args.at, context)
    if args.start:
        start = parse(args.start, tz, date_hour=0.0)
    else:
        start = at if at is not None else _date_or_now(None, context)
    end = parse(args.until, tz, date_hour=24.0) if args.until else start + args.days
    if end <= start:
        raise ValueError("--until must follow the start of the search")
    kw = {
        "toward": toward,
        "first_leg": Mu.resolve_direction(args.first_leg),
        "ayanamsa": args.ayanamsa,
    }
    birth = (chart.grahas["Moon"], chart.asc.sign)
    if at is not None:
        _record_exposure(at, context, "muhurta")
        verdict = Mu.check(profile, at, context.lat, context.lon, *birth, **kw)
        print(Mu.verdict_report(verdict, tz, profile))
        print()
    _record_exposure_window(start, end, context, "muhurta")
    hours = Mu.parse_hours(args.hours) if args.hours else None
    choices = Mu.find(
        profile, start, end, context.lat, context.lon, *birth, tz=tz, hours=hours, **kw
    )
    if args.by == "time":
        choices.sort(key=lambda c: c.start)
    print(Mu.find_report(choices[: args.top], tz, profile))


def cmd_panchanga(sub, args):
    from . import panchanga as Pa

    context = _context(sub, args)
    jd = _date_or_now(args.on, context)
    result = Pa.compute(jd, context.lat, context.lon, args.ayanamsa)
    _record_exposure(jd, context, "panchanga")
    if args.format == "human":
        print(
            f"  context     {context.place or '-'} "
            f"({context.lat:.4f}, {context.lon:.4f}, {context.timezone})"
        )
        print(f"  moment      {fmt(jd, context.timezone, True)}")
        print(result)
    else:
        payload = {
            **asdict(result),
            "moment": to_datetime(jd, context.timezone).isoformat(),
            "context": asdict(context),
        }
        _emit(payload, args.format)


def cmd_varsha(sub, args):
    from . import tajika as T

    context = _context(sub, args)
    chart = sub.chart(ayanamsa=args.ayanamsa, node=args.node)
    year_index = args.age
    if year_index is None:
        year_index = max(0, int((_date_or_now(None, context) - chart.jd) / 365.2563))
    print(
        T.report(
            chart,
            year_index,
            context.timezone,
            observer_lat=context.lat,
            observer_lon=context.lon,
        )
    )


def cmd_prashna(sub, args):
    from . import prashna as Pr
    from .chart import Chart

    context = _context(sub, args)
    jd = _date_or_now(args.at, context)
    c = Chart(
        jd=jd,
        lat=context.lat,
        lon=context.lon,
        tz=context.timezone,
        ayanamsa=args.ayanamsa,
        node=args.node,
    )
    _record_exposure(jd, context, "prashna")
    print(Pr.report(c, args.question, args.topic, args.number, context.timezone))


def cmd_conditional(sub, args):
    from . import conditional as C

    print(
        C.report(
            sub.chart(ayanamsa=args.ayanamsa, node=args.node),
            _context(sub, args).timezone,
        )
    )


def cmd_everything(sub, args):
    """Every technique in the package, for a date range. No filtering."""
    from . import reading as RD

    context = _context(sub, args)
    c = sub.chart(ayanamsa=args.ayanamsa, node=args.node)
    trees, cache = RD._trees(c), {}
    start = args.start or _today(context)
    rows = []
    for d in range(args.days):
        jd = _civil_day_jd(start, d, context)
        rows.append(
            RD.everything(
                c,
                jd,
                context.timezone,
                trees,
                cache,
                observer_lat=context.lat,
                observer_lon=context.lon,
            )
        )
        _record_exposure(jd, context, "everything")
    _emit(rows if args.days != 1 else rows[0], args.format)


def cmd_sbc(sub, args):
    """The sarvatobhadra chakra, day by day.

    Every strike is printed with the ray that carried it, so a claim can be
    checked against the grid by hand rather than taken on trust.
    """
    from . import panchanga as PA
    from . import sbc as SB

    context = _context(sub, args)
    c = sub.chart(ayanamsa=args.ayanamsa, node=args.node)
    pan = PA.compute(c.jd, c.lat, c.lon, c.ayanamsa)
    natal = SB.natal_cells(c, SB.tithi_group(pan.tithi), pan.vara)
    janma = {k: v for k, v in natal.items() if v in ("janma nakshatra", "janma rasi")}
    print(f"janma tithi {pan.tithi} ({SB.tithi_group(pan.tithi)}), vara lord {pan.vara}")
    print(
        f"{len(natal)} sensitive cells; "
        f"janma-critical: "
        f"{', '.join(SB.CONTENT[k] for k in sorted(janma))}\n"
    )
    start = args.start or _today(context)
    for i in range(args.days):
        jd = _civil_day_jd(start, i, context)
        hits = SB.strikes(c, jd, natal)
        jhits = SB.strikes(c, jd, janma)
        bad = sum(1 for h in jhits if not h.benefic)
        date = fmt(jd, context.timezone)
        flag = "CLEAR" if bad == 0 else f"{bad} malefic on janma"
        print(f"{date}  net {SB.score(c, jd, natal):+7.2f}   janma: {flag}")
        if args.verbose:
            for h in sorted(hits, key=lambda x: (not x.benefic, x.graha)):
                mark = "+" if h.benefic else "-"
                print(
                    f"      {mark} {h.graha:8s} {h.arm:5s} -> {SB.CONTENT[h.cell]:14s} [{h.target}]"
                )
        _record_exposure(jd, context, "sbc")


def cmd_rare(sub, args):
    """Day-by-day read from the rarer chakras and cycles."""
    from . import ashtakavarga as AV
    from . import dashas as D
    from . import panchanga as PA
    from . import rare as R
    from .ephemeris import NAKSHATRAS, positions

    context = _context(sub, args)
    c = sub.chart(ayanamsa=args.ayanamsa, node=args.node)
    tree = D.vimshottari(c)
    sav = AV.sarva(AV.bhinna(c))
    janma = c.grahas["Moon"].nakshatra
    TARA = [
        "Janma",
        "Sampat",
        "Vipat",
        "Kshema",
        "Pratyari",
        "Sadhaka",
        "Vadha",
        "Mitra",
        "Ati-mitra",
    ]
    good = {1, 3, 5, 7, 8}
    print(
        f"{'date':13s}{'vara':9s}{'prana':16s}{'moon':10s}{'nakshatra':11s}"
        f"{'tara':10s}{'SAV':>4s} {'Sat':6s}{'bird/act':14s}{'kota':7s}"
        f"{'SBC':10s}{'latta':7s}{'ghat':6s}{'bhrigu':9s}"
    )
    start = args.start or _today(context)
    for d in range(args.days):
        jd = _civil_day_jd(start, d, context)
        m = positions(jd, args.ayanamsa, args.node)
        pc = PA.compute(jd, context.lat, context.lon, args.ayanamsa)
        chain = D.active(tree, jd)
        prana = "-".join(p.lord for p in chain[3:5]) or "-"
        t = ((m["Moon"].nakshatra - janma) % 27) % 9
        kk = AV.kakshya_transit(c, m, "Saturn")
        pp = R.pancha_pakshi(
            c,
            jd,
            observer_lat=context.lat,
            observer_lon=context.lon,
        )
        siege = ",".join(r["graha"] for r in R.kota_chakra(c, jd)["under_siege"])
        sbc = ";".join(f"{x['graha']}" for x in R.sarvatobhadra(c, jd))
        lat = ";".join(x["graha"] for x in R.latta(c, jd))
        gh = ";".join(
            g.split()[1]
            for g in R.ghataka(
                c,
                jd,
                observer_lat=context.lat,
                observer_lon=context.lon,
            )
        )
        bh = ";".join(f"{x['graha']}{x['orb']:.1f}" for x in R.bhrigu_hits(c, jd, orb=4))
        print(
            f"{fmt(jd, context.timezone):13s}{pc.vara:9s}{prana:16s}"
            f"{SIGNS[m['Moon'].sign][:3]} h"
            f"{(m['Moon'].sign - c.asc.sign) % 12 + 1:<6d}"
            f"{NAKSHATRAS[m['Moon'].nakshatra][:10]:11s}"
            f"{TARA[t] + ('' if t in good else '*'):10s}"
            f"{sav[m['Moon'].sign]:4d} "
            f"{('act' if kk['active'] else 'INERT'):6s}"
            f"{pp['bird'][:3] + '/' + pp['activity']:14s}{siege or '-':7s}"
            f"{sbc or '-':10s}{lat or '-':7s}{gh or '-':6s}{bh or '-':9s}"
        )
        _record_exposure(jd, context, "rare")
    print("\n  * = inauspicious tara")


def _domains(args) -> list[str]:
    values = [item.strip() for item in args.domains.split(",") if item.strip()]
    invalid = [item for item in values if item not in DOMAINS]
    if invalid:
        raise ValueError(f"unknown domain {invalid[0]!r}")
    return list(dict.fromkeys(values))


def _polarity(args) -> int | None:
    return {"any": None, "gain": 1, "loss": -1, "neutral": 0}[args.polarity]


def _learn_setup(sub, args, domain: str, cutoff: float):
    from . import learn as L
    from .subjects import Event

    context = _context(sub, args)
    c = sub.chart(ayanamsa=args.ayanamsa, node=args.node)
    wins = L.windows(
        parse(args.since, context.timezone, date_hour=0),
        cutoff,
        timezone=context.timezone,
    )
    if not wins:
        raise ValueError("training interval contains no complete windows")
    hyps = [h for h in H.LIBRARY if not h.name.startswith("CONTROL")]
    polarity = _polarity(args)
    prototype_polarity = 0 if polarity is None else polarity
    proto = Event(
        "2020-01-01",
        "prototype",
        (domain,),
        prototype_polarity,
        magnitude=args.min_magnitude,
    )
    X = L.featurize(c, wins, hyps, proto, timezone=context.timezone)
    y = L.label(
        sub,
        wins,
        domain,
        polarity=polarity,
        min_magnitude=args.min_magnitude,
    )
    calendar_X = L.calendar_features(wins, context.timezone)
    return c, wins, hyps, proto, X, calendar_X, y


def cmd_learn(sub, args):
    from . import learn as L

    context = _context(sub, args)
    cutoff = (
        parse(args.until, context.timezone, date_hour=0)
        if args.until
        else parse(_current_stamp(context))
    )
    for domain in _domains(args):
        c, wins, hyps, proto, X, calendar_X, y = _learn_setup(sub, args, domain, cutoff)
        print(
            f"=== LEARNING — {domain}; {len(wins)} complete "
            f"{L.WINDOW_DAYS}-day windows; {int(y.sum())} events ===\n"
        )
        res = L.prequential(X, y, burn_in=args.burn_in, calendar_X=calendar_X)
        print(L.report(res))
        if res["n_scored"]:
            print()
            print(L.calibration(res["y"], res["p"], bins=4))
        names = [f"{h.name} [{kind}]" for h in hyps for kind in ("mean", "peak")]
        scaler = L.Standardizer().fit(X)
        c_scaler = L.Standardizer().fit(calendar_X)
        full_X = np.hstack([c_scaler.transform(calendar_X), scaler.transform(X)])
        full_names = [
            "calendar annual sin",
            "calendar annual cos",
            "calendar weekly sin",
            "calendar weekly cos",
            "calendar trend",
            *names,
        ]
        print()
        print(L.BayesLogistic().fit(full_X, y).weight_table(full_names, top=8))
        print(
            "\n  Note: model fitting is walk-forward, but techniques created "
            "after these outcomes remain retrospective. Only sealed future "
            "trials are confirmatory.\n"
        )


def cmd_forecast(sub, args):
    """Fit on everything known, then seal predictions for coming windows."""
    from . import learn as L
    from . import ledger, provenance

    context = _context(sub, args)
    if args.start:
        start_dt = to_datetime(
            parse(args.start, context.timezone, date_hour=0),
            context.timezone,
        )
    else:
        tomorrow = now(context.timezone).date() + dt.timedelta(days=1)
        start_dt = dt.datetime.combine(
            tomorrow,
            dt.time.min,
            tzinfo=now(context.timezone).tzinfo,
        )
    start = parse(start_dt.isoformat())
    cutoff = parse(args.until, context.timezone, date_hour=0) if args.until else start
    if cutoff > start:
        raise ValueError("training cutoff cannot follow forecast start")
    future = L.future_windows(start, args.ahead, timezone=context.timezone)
    sealed = 0
    for domain in _domains(args):
        c, wins, hyps, proto, X, calendar_X, y = _learn_setup(sub, args, domain, cutoff)
        result = L.prequential(X, y, burn_in=args.burn_in, calendar_X=calendar_X)
        powered = result["n_scored"] >= L.MIN_SCORED and result["n_events"] >= L.MIN_EVENTS
        signal = powered and result["skill"] > 0 and result["skill_p"] < 0.05
        status = "prospective-test-eligible" if signal else "experimental"
        # The forecast always prints. Skill is still measured and still travels
        # with every sealed record, but it no longer suppresses the display.
        print(f"=== FORECAST — {domain}; status={status} ===")

        x_scaler = L.Standardizer().fit(X)
        c_scaler = L.Standardizer().fit(calendar_X)
        scaled_X = x_scaler.transform(X)
        scaled_C = c_scaler.transform(calendar_X)
        full_model = L.BayesLogistic().fit(np.hstack([scaled_C, scaled_X]), y)
        calendar_model = L.BayesLogistic(tau=0.5).fit(scaled_C, y)
        future_X = L.featurize(
            c,
            future,
            hyps,
            proto,
            timezone=context.timezone,
        )
        future_C = L.calendar_features(future, context.timezone)
        scaled_future_X = x_scaler.transform(future_X)
        scaled_future_C = c_scaler.transform(future_C)
        probabilities = full_model.predict(np.hstack([scaled_future_C, scaled_future_X]))
        opponents = calendar_model.predict(scaled_future_C)
        manifest = provenance.manifest(
            sub,
            technique_ids=[h.technique_id for h in hyps],
            config={
                "domain": domain,
                "polarity": args.polarity,
                "min_magnitude": args.min_magnitude,
                "ayanamsa": args.ayanamsa,
                "node": args.node,
                "window_days": L.WINDOW_DAYS,
                "training_cutoff": to_datetime(cutoff, context.timezone).isoformat(),
                "timezone": str(context.timezone),
            },
        )
        for (a, b), probability, opponent in zip(future, probabilities, opponents, strict=True):
            start_iso = to_datetime(a, context.timezone).isoformat()
            end_iso = to_datetime(b, context.timezone).isoformat()
            print(
                f"  {start_iso} .. {end_iso}  p={probability:.3f}  "
                f"calendar={opponent:.3f}  "
                f"lift={probability / max(opponent, 1e-9):.2f}x"
            )
            _record_exposure_window(a, b, context, "forecast")
            if args.seal:
                ledger.predict(
                    sub.name,
                    start_iso,
                    end_iso,
                    domain,
                    float(probability),
                    float(opponent),
                    FORECAST_MODEL,
                    timezone=context.timezone,
                    trial_id=args.trial_id,
                    provenance=manifest,
                    experimental=not bool(args.trial_id),
                )
                sealed += 1
        print()
    if args.seal:
        print(f"  sealed {sealed} prediction(s); {ledger.verify()[1]}")
    elif sealed == 0:
        print("  nothing sealed")


def cmd_predict(sub, args):
    """Technique-attributed reading: what fires, when, and on what grounds."""
    from . import predict as P

    context = _context(sub, args)
    today = now(context.timezone).date()
    start = dt.date.fromisoformat(args.start) if args.start else today + dt.timedelta(days=1)
    end = dt.date.fromisoformat(args.until) if args.until else start + dt.timedelta(days=182)
    if end <= start:
        raise ValueError("--until must follow --start")
    readings = P.read(
        sub,
        args.domain,
        start,
        end,
        window_days=args.window_days,
        ayanamsa=args.ayanamsa,
        node=args.node,
        timezone=context.timezone,
    )
    for reading in readings:
        _record_exposure_window(
            parse(reading.start.isoformat(), context.timezone),
            parse(reading.end.isoformat(), context.timezone),
            context,
            "predict",
        )
    print(P.narrate(readings, args.domain))


def cmd_resolve(sub, args):
    from . import ledger

    ledger.resolve(
        args.window,
        args.domain,
        args.occurred == "yes",
        args.detail,
        prediction_id=args.prediction_id,
        occurrence_at=args.occurrence_at,
        polarity={"gain": 1, "loss": -1, "neutral": 0}.get(args.polarity),
        magnitude=args.magnitude,
        source=args.source,
    )
    print(ledger.verify()[1])


def cmd_scoreboard(sub, args):
    from . import ledger

    print(ledger.scoreboard())


def cmd_anchor(sub, args):
    from . import ledger

    _emit(ledger.head_commitment(), args.format)


def cmd_doctor(sub, args):
    from . import data_manifest, ledger
    from .ephemeris import backend_info
    from .storage import user_data_dir

    backend = backend_info()
    manifest_errors = data_manifest.verify_manifest()
    manifest_warnings = data_manifest.manifest_warnings()
    ledger_ok, ledger_message = ledger.verify()
    ids = [h.technique_id for h in H.LIBRARY]
    source_gaps = sum(not h.source for h in H.LIBRARY)
    warnings = [
        *(
            [
                "Moshier fallback is active; configure SE_EPHE_PATH for "
                "licensed Swiss Ephemeris files"
            ]
            if backend["actual"] == "moshier"
            else []
        ),
        *manifest_warnings,
        *([f"{source_gaps} technique encodings lack exact citations"] if source_gaps else []),
    ]
    report = {
        "status": (
            "error" if not ledger_ok or manifest_errors else "warning" if warnings else "ok"
        ),
        "ephemeris": backend,
        "warnings": warnings,
        "ledger": {"ok": ledger_ok, "message": ledger_message},
        "user_data_dir": str(user_data_dir()),
        "data_manifest_errors": manifest_errors,
        "data_manifest_warnings": manifest_warnings,
        "techniques": {
            "count": len(ids),
            "unique_ids": len(ids) == len(set(ids)),
            "missing_source_citations": source_gaps,
        },
    }
    if args.format == "human":
        print(f"  status             {report['status']}")
        print(f"  ephemeris actual   {backend['actual']}")
        for warning in warnings:
            print(f"  warning            {warning}")
        print(f"  ledger             {ledger_message}")
        print(f"  user data          {report['user_data_dir']}")
        print(
            f"  data checks        {'pass' if not manifest_errors else '; '.join(manifest_errors)}"
        )
        print(
            f"  technique ids      "
            f"{'unique' if report['techniques']['unique_ids'] else 'DUPLICATE'}"
        )
        print(f"  source gaps        {report['techniques']['missing_source_citations']}")
    else:
        _emit(report, args.format)


def cmd_techniques(sub, args):
    if args.technique_id:
        technique = H.by_id(args.technique_id)
        payload = {
            **technique.metadata(),
            "rule": pyinspect.getdoc(technique.score) or "",
        }
        if args.at:
            from .subjects import Event

            context = _context(sub, args)
            jd = parse(args.at, context.timezone)
            event = Event(
                to_datetime(jd, context.timezone).date().isoformat(),
                "probe",
                (args.domain,),
                0,
            )
            payload["probe"] = {
                "moment": to_datetime(jd, context.timezone).isoformat(),
                "domain": args.domain,
                "score": technique.score(
                    sub.chart(ayanamsa=args.ayanamsa, node=args.node),
                    jd,
                    event,
                ),
            }
        if args.format == "human":
            for key, value in payload.items():
                print(f"  {key:22s} {value}")
        else:
            _emit(payload, args.format)
        return
    payload = H.registry()
    if args.format == "human":
        print(f"{'id':48s}{'status':14s}{'introduced':12s} source")
        for row in payload:
            print(
                f"{row['id'][:47]:48s}{row['status'][:13]:14s}"
                f"{row['introduced_at']:12s}{row['source'] or 'UNVERIFIED'}"
            )
    else:
        _emit(payload, args.format)


def cmd_inspect(sub, args):
    from . import reading

    context = _context(sub, args)
    jd = _date_or_now(args.at, context)
    payload = reading.everything(
        sub.chart(ayanamsa=args.ayanamsa, node=args.node),
        jd,
        context.timezone,
        observer_lat=context.lat,
        observer_lon=context.lon,
    )
    payload["moment"] = to_datetime(jd, context.timezone).isoformat()
    payload["context"] = asdict(context)
    if args.layers:
        selected = {item.strip() for item in args.layers.split(",") if item.strip()}
        unknown = selected - payload.keys()
        if unknown:
            raise ValueError(f"unknown inspect layer {sorted(unknown)[0]!r}")
        payload = {
            key: value
            for key, value in payload.items()
            if key in selected or key in {"date", "moment", "context"}
        }
    _record_exposure(jd, context, "inspect")
    _emit(payload, args.format)


def cmd_sensitivity(sub, args):
    offsets = np.arange(-args.minutes, args.minutes + args.step / 2, args.step)
    divisions = [int(item.strip()) for item in args.vargas.split(",") if item.strip()]
    snapshots = []
    for offset in offsets:
        chart = sub.shifted(float(offset)).chart(
            ayanamsa=args.ayanamsa,
            node=args.node,
        )
        row = {
            "offset_minutes": float(offset),
            "ascendant_sign": SIGNS[chart.asc.sign],
            "ascendant_degree": chart.asc.longitude,
        }
        for division in divisions:
            divided = chart.d(division)
            row[f"D{division}_ascendant"] = SIGNS[divided.asc.sign]
            for graha in GRAHAS:
                row[f"D{division}_{graha}"] = SIGNS[divided.grahas[graha].sign]
        snapshots.append(row)
    if args.format == "human":
        varying = []
        keys = [key for key in snapshots[0] if key != "offset_minutes"]
        for key in keys:
            values = [str(row[key]) for row in snapshots]
            unique = list(dict.fromkeys(values))
            if len(unique) > 1:
                varying.append((key, unique))
        print(f"  birth-time range ±{args.minutes:g} min; {len(snapshots)} samples")
        if not varying:
            print("  all requested placements are stable")
        for key, values in varying:
            print(f"  {key:28s} changes: {', '.join(values)}")
    else:
        _emit(snapshots, args.format)


def cmd_trial(sub, args):
    from . import learn as L
    from . import trials

    context = _context(sub, args)
    if args.trial_cmd == "list":
        rows = [
            {
                "trial_id": row["trial_id"],
                "name": row["name"],
                "status": trials.status(row),
                "start": row["start"],
                "end": row["end"],
                "endpoint": row["endpoint"],
                "domains": row["domains"],
                "technique_count": len(row["technique_ids"]),
            }
            for row in trials.registrations()
        ]
        if args.format == "human":
            if not rows:
                print("  no registered trials")
            for row in rows:
                print(f"  {row['trial_id']}  {row['status']:10s} {row['name']} ({row['endpoint']})")
        else:
            _emit(rows, args.format)
        return
    if args.trial_cmd == "score":
        result = trials.efficacy(args.trial_id)
        if args.format == "human":
            for key, value in result.items():
                print(f"  {key:24s} {value}")
        else:
            _emit(result, args.format)
        return
    technique_ids = (
        [h.technique_id for h in H.LIBRARY if not h.name.startswith("CONTROL")]
        if args.techniques == "all"
        else [item.strip() for item in args.techniques.split(",") if item.strip()]
    )
    domains = [item.strip() for item in args.domains.split(",") if item.strip()]
    checkpoints = [int(item.strip()) for item in args.checkpoints.split(",") if item.strip()]
    start = to_datetime(
        parse(args.start, context.timezone, date_hour=0), context.timezone
    ).isoformat()
    end = to_datetime(parse(args.end, context.timezone, date_hour=0), context.timezone).isoformat()
    row = trials.register(
        sub,
        name=args.name,
        start=start,
        end=end,
        domains=domains,
        technique_ids=technique_ids,
        endpoint=args.endpoint,
        polarity=args.polarity,
        min_magnitude=args.min_magnitude,
        checkpoints=checkpoints,
        ayanamsa=args.ayanamsa,
        node=args.node,
        timezone=str(context.timezone),
        window_days=L.WINDOW_DAYS,
        model=FORECAST_MODEL,
    )
    _emit(
        {
            "trial_id": row["trial_id"],
            "name": row["name"],
            "start": row["start"],
            "end": row["end"],
            "ledger_hash": row["hash"],
        },
        args.format,
    )


def cmd_rate(sub, args) -> None:
    """Log today's self-rating.  Do this BEFORE reading the day's panchanga."""
    from . import daily

    context = _context(sub, args)
    date = args.date or _today(context)
    r = daily.Rating(
        date=date,
        mood=args.mood,
        energy=args.energy,
        self_presentation=args.self_presentation,
        social_ease=args.social_ease,
        focus=args.focus,
        note=args.note,
    )
    row = daily.log(r, timezone=context.timezone)
    n = len(daily.load())
    if args.format == "human":
        print(f"  logged {date} and sealed to the ledger.  {n} day(s) on record.")
        if n < daily.FORMAL_CHECKPOINTS[0]:
            print(f"  {daily.FORMAL_CHECKPOINTS[0] - n} more before formal inference.")
    else:
        _emit(
            {
                "rating": row,
                "n_logged": n,
                "next_checkpoint": next(
                    (value for value in daily.FORMAL_CHECKPOINTS if value > n),
                    None,
                ),
            },
            args.format,
        )


def cmd_ratings(sub, args) -> None:
    from . import daily

    if args.format == "human":
        print(
            daily.score(
                sub,
                field=args.field,
                n_perm=args.nulls,
                ayanamsa=args.ayanamsa,
                node=args.node,
            )
        )
    else:
        _emit(
            daily.analyze(
                sub,
                field=args.field,
                n_perm=args.nulls,
                ayanamsa=args.ayanamsa,
                node=args.node,
            ),
            args.format,
        )


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="jyotisha",
        description="Deterministic Jyotisha calculations and sealed experiments.",
    )
    ap.add_argument("--subject", default="example", choices=sorted(SUBJECTS))
    ap.add_argument("--ayanamsa", default="lahiri", choices=sorted(AYANAMSAS))
    ap.add_argument("--node", default="true", choices=["true", "mean"])
    ap.add_argument("--timezone", default=None, help="observer IANA timezone")
    ap.add_argument("--lat", type=float, default=None, help="observer latitude")
    ap.add_argument("--lon", type=float, default=None, help="observer longitude")
    ap.add_argument("--place", default=None, help="observer place label")
    ap.add_argument(
        "--format",
        choices=["human", "json", "jsonl", "csv"],
        default="human",
    )
    sp = ap.add_subparsers(dest="cmd", required=True)

    p = sp.add_parser("chart")
    p.add_argument("--vargas", default="9,10,24,7,12,30,60")
    sp.add_parser("av")
    p = sp.add_parser("dasha")
    p.add_argument("--on", default=None, help="ISO moment; defaults to now")
    p = sp.add_parser("ladder")
    p.add_argument("--on", default=None, help="ISO moment; defaults to now")
    p.add_argument("--level", type=int, choices=range(2, 6), default=4)
    p = sp.add_parser("transit")
    p.add_argument("--on", default=None, help="ISO moment; defaults to now")
    p = sp.add_parser("events")
    p.add_argument("--start", default=None, help="ISO date; defaults to today")
    p.add_argument("--end", default=None, help="defaults to 18 months ahead")
    p = sp.add_parser("backtest")
    p.add_argument("--nulls", type=_positive_int, default=999)
    p.add_argument(
        "--null-mode",
        dest="null_mode",
        default="matched",
        choices=["uniform", "seasonal", "matched"],
    )
    p.add_argument("--seed", type=int, default=7)
    p.add_argument(
        "--workers",
        type=_nonnegative_int,
        default=0,
        help="worker processes; 0 selects up to eight for larger runs",
    )
    p.add_argument("--no-precision-gate", action="store_true")
    p = sp.add_parser("ayanamsa")
    p.add_argument("--nulls", type=_positive_int, default=999)
    for name in ("learn", "forecast"):
        p = sp.add_parser(name)
        p.add_argument("--since", default="2019-01-01")
        p.add_argument("--until", default=None, help="training cutoff")
        p.add_argument(
            "--domains",
            default="career,education,recognition,relationship,money,home,travel,conflict",
        )
        p.add_argument(
            "--polarity",
            choices=["any", "gain", "loss", "neutral"],
            default="any",
        )
        p.add_argument("--min-magnitude", type=int, choices=range(1, 6), default=2)
        p.add_argument("--burn-in", dest="burn_in", type=_positive_int, default=60)
        if name == "forecast":
            p.add_argument("--ahead", type=_positive_int, default=6)
            p.add_argument("--start", default=None)
            p.add_argument("--seal", action="store_true")
            p.add_argument("--trial-id", default="")
    p = sp.add_parser("predict", help="technique-attributed reading for a domain")
    p.add_argument("--domain", default="career")
    p.add_argument("--start", default=None, help="default: tomorrow")
    p.add_argument("--until", default=None, help="default: six months out")
    p.add_argument("--window-days", dest="window_days", type=_positive_int, default=14)
    p = sp.add_parser("resolve")
    p.add_argument("--prediction-id", default=None)
    p.add_argument("--window", default=None)
    p.add_argument("--domain", default=None)
    p.add_argument("--occurred", choices=["yes", "no"], required=True)
    p.add_argument("--occurrence-at", default=None)
    p.add_argument("--polarity", choices=["gain", "loss", "neutral"], default=None)
    p.add_argument("--magnitude", type=int, choices=range(1, 6), default=None)
    p.add_argument("--source", default="")
    p.add_argument("--detail", default="")
    sp.add_parser("scoreboard")
    sp.add_parser("anchor")
    sp.add_parser("doctor")
    p = sp.add_parser("techniques")
    p.add_argument("technique_id", nargs="?", default=None)
    p.add_argument("--at", default=None, help="optional probe moment")
    p.add_argument("--domain", choices=sorted(DOMAINS), default="career")
    p = sp.add_parser("inspect")
    p.add_argument("--at", default=None, help="ISO moment; defaults to now")
    p.add_argument("--layers", default=None, help="comma-separated output layers")
    p = sp.add_parser("sensitivity")
    p.add_argument("--minutes", type=_nonnegative_float, default=30)
    p.add_argument("--step", type=_positive_float, default=5)
    p.add_argument("--vargas", default="1,9,10,24,60")
    p = sp.add_parser("trial")
    trial_sp = p.add_subparsers(dest="trial_cmd", required=True)
    trial_sp.add_parser("list")
    trial_score = trial_sp.add_parser("score")
    trial_score.add_argument("--trial-id", required=True)
    register = trial_sp.add_parser("register")
    register.add_argument("--name", required=True)
    register.add_argument("--start", required=True)
    register.add_argument("--end", required=True)
    register.add_argument("--domains", required=True)
    register.add_argument("--techniques", default="all")
    register.add_argument(
        "--endpoint",
        choices=["forecast-windows"],
        default="forecast-windows",
    )
    register.add_argument(
        "--polarity",
        choices=["any", "gain", "loss", "neutral"],
        default="any",
    )
    register.add_argument("--min-magnitude", type=int, choices=range(1, 6), default=2)
    register.add_argument("--checkpoints", default="30,60,120")
    for name in ("strength", "states", "points", "jaimini", "yogas"):
        sp.add_parser(name)
    p = sp.add_parser("panchanga")
    p.add_argument("--on", default=None, help="ISO moment; defaults to now")
    p = sp.add_parser("muhurta", help="daily timing windows, or --find a moment for an act")
    p.add_argument(
        "--start", default=None, help="ISO date (day reports use its noon) or moment for --find"
    )
    p.add_argument("--days", type=_positive_int, default=7)
    p.add_argument(
        "--find",
        default=None,
        metavar="ACT",
        help="rank windows for an act: general, education, travel or home",
    )
    p.add_argument("--at", default=None, help="with --find: judge this moment first ('now')")
    p.add_argument("--until", default=None, help="with --find: end; a bare date runs to midnight")
    p.add_argument("--hours", default=None, help="with --find: allowed local hours, 08:00-20:00")
    p.add_argument("--toward", default=None, help="travel: destination direction (W, NW or 276)")
    p.add_argument("--first-leg", default=None, help="travel: first leg's direction if different")
    p.add_argument("--top", type=_positive_int, default=8)
    p.add_argument("--by", choices=["score", "time"], default="score", help="order of --find")
    p = sp.add_parser("varsha")
    p.add_argument("--age", type=_nonnegative_int, default=None, help="solar-return index")
    p = sp.add_parser("prashna")
    p.add_argument("--question", required=True)
    p.add_argument("--topic", default=None)
    p.add_argument("--at", default=None, help="actual question moment")
    p.add_argument("--number", type=int, choices=range(1, 109), default=None)
    sp.add_parser("conditional")
    p = sp.add_parser("everything")
    p.add_argument("--start", default=None)
    p.add_argument("--days", type=_positive_int, default=1)
    p = sp.add_parser("rare")
    p.add_argument("--start", default=None)
    p.add_argument("--days", type=_positive_int, default=7)
    p = sp.add_parser("sbc")
    p.add_argument("--start", default=None)
    p.add_argument("--days", type=_positive_int, default=7)
    p.add_argument("--verbose", action="store_true")
    p = sp.add_parser("rate")
    for f in ("mood", "energy", "self-presentation", "social-ease", "focus"):
        p.add_argument("--" + f, type=int, required=True, help="1 (low) to 5 (high)")
    p.add_argument("--date", default=None, help="defaults to today")
    p.add_argument("--note", default="")
    p = sp.add_parser("ratings")
    p.add_argument(
        "--field",
        default="all",
        choices=["all", *("mood", "energy", "self_presentation", "social_ease", "focus")],
    )
    p.add_argument("--nulls", type=_positive_int, default=5000)
    p = sp.add_parser("rectify")
    p.add_argument("--span", type=_positive_float, default=30)
    p.add_argument("--step", type=_positive_float, default=5)
    p.add_argument("--nulls", type=_positive_int, default=150)

    args = ap.parse_args()
    structured_commands = {
        "anchor",
        "backtest",
        "doctor",
        "everything",
        "inspect",
        "panchanga",
        "rate",
        "ratings",
        "sensitivity",
        "techniques",
        "trial",
    }
    if args.format != "human" and args.cmd not in structured_commands:
        ap.error(
            f"--format {args.format} is not supported by {args.cmd}; "
            "use inspect for canonical structured output"
        )
    sub = SUBJECTS[args.subject]
    commands = {
        "chart": cmd_chart,
        "av": cmd_av,
        "dasha": cmd_dasha,
        "ladder": cmd_ladder,
        "transit": cmd_transit,
        "events": cmd_events,
        "backtest": cmd_backtest,
        "ayanamsa": cmd_ayanamsa,
        "rectify": cmd_rectify,
        "learn": cmd_learn,
        "forecast": cmd_forecast,
        "predict": cmd_predict,
        "resolve": cmd_resolve,
        "scoreboard": cmd_scoreboard,
        "anchor": cmd_anchor,
        "doctor": cmd_doctor,
        "techniques": cmd_techniques,
        "inspect": cmd_inspect,
        "sensitivity": cmd_sensitivity,
        "trial": cmd_trial,
        "strength": cmd_strength,
        "states": cmd_states,
        "points": cmd_points,
        "jaimini": cmd_jaimini,
        "yogas": cmd_yogas,
        "muhurta": cmd_muhurta,
        "panchanga": cmd_panchanga,
        "varsha": cmd_varsha,
        "prashna": cmd_prashna,
        "rare": cmd_rare,
        "everything": cmd_everything,
        "conditional": cmd_conditional,
        "rate": cmd_rate,
        "ratings": cmd_ratings,
        "sbc": cmd_sbc,
    }
    try:
        commands[args.cmd](sub, args)
    except (KeyError, ValueError, RuntimeError) as exc:
        ap.error(str(exc))


if __name__ == "__main__":
    main()
