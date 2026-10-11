#!/usr/bin/env python3
"""Zamienia PDF z harmonogramem (Wzornictwo przemysłowe, rok 2) na data/plan.json.

Dzień tygodnia wynika z położenia wpisu na stronie: każdy dzień zaczyna się od wiersza
godzin „8 - 9”. Przy nieznanym formacie wpisu skrypt kończy się błędem, żeby nie
opublikować po cichu zepsutego planu.
"""
import datetime
import json
import pathlib
import re
import sys

import pdfplumber

TYPY = {"w": "wykład", "lab": "laboratorium", "proj": "projekt", "ćw": "ćwiczenia", "cw": "ćwiczenia"}
TIME = r"(\d{1,2})[:.](\d{2})\s*-\s*(\d{1,2})[:.](\d{2})"
TYP = r"(W|lab|proj|ćw)"


def hhmm(h, m):
    return f"{int(h):02d}:{m}"


def weeks(s):
    """'1t.' -> 'A' (tydzień I), '2t.' -> 'B', '6-15t.' -> [6, 15]. Zwraca (wartość, tekst bez tego zapisu)."""
    m = re.search(r"(?:(\d+)\s*-\s*(\d+)|(\d+))\s*t\.", s)
    if not m:
        return None, s
    if m.group(3):
        n = int(m.group(3))
        val = {1: "A", 2: "B"}.get(n, [n, n])
    else:
        val = [int(m.group(1)), int(m.group(2))]
    return val, s[:m.start()] + s[m.end():]


def lecturer_room(s):
    s = s.strip(" ;,")
    if ";" in s:
        who, where = s.split(";", 1)
    elif " - " in s:
        who, where = s.rsplit(" - ", 1)
    elif re.match(r"(dr|prof|mgr|inż)\b", s, re.I):
        who, _, where = s.partition(",")
    else:
        who, where = "", s
    where = where.strip(" ;,")
    m = re.search(r"ISP,?\s*s\.\s*\d+", where)
    if m:
        where = m.group(0)
    return who.strip(), where


def parse_block(lines):
    text = [t.strip() for t in lines]
    # wpis wielowierszowy: tytuł / prowadzący; sala / „W - 8:15-9:00” / „lab - 9:15-11:00”
    if len(text) >= 3 and all(re.match(rf"^{TYP}\s*-\s*{TIME}$", t, re.I) for t in text[2:]):
        who, room = lecturer_room(text[1])
        out = []
        for t in text[2:]:
            m = re.match(rf"^{TYP}\s*-\s*{TIME}$", t, re.I)
            out.append(dict(p=text[0], t=TYPY[m.group(1).lower()], s=hhmm(m.group(2), m.group(3)),
                            k=hhmm(m.group(4), m.group(5)), r=room, w=who))
        return out
    one = " ".join(text)
    tm = re.search(rf",?\s*(?:w\s+)?g\.\s*{TIME}\s*$", one)
    if not tm:
        raise ValueError(f"Nie rozpoznano godzin we wpisie: {one!r}")
    mt = re.match(rf"^(.+?)\s-\s{TYP}\s-\s(.+)$", one[:tm.start()], re.I)
    if not mt:
        raise ValueError(f"Nie rozpoznano przedmiotu/typu we wpisie: {one!r}")
    tyg, rest = weeks(mt.group(3))
    who, room = lecturer_room(rest)
    e = dict(p=mt.group(1).strip(), t=TYPY[mt.group(2).lower()], s=hhmm(tm.group(1), tm.group(2)),
             k=hhmm(tm.group(3), tm.group(4)), r=room, w=who)
    if tyg:
        e["tyg"] = tyg
    return [e]


def main(pdf_path, out_path):
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        words = page.extract_words()
        starts = sorted(w["top"] for w in words if w["x0"] < 165 and w["text"] == "8")
        if len(starts) != 5:
            raise ValueError(f"Spodziewano się 5 dni, znaleziono {len(starts)} – zmienił się układ PDF-a?")
        foot = [w["top"] for w in words if w["text"] == "Oznaczenia"]
        bottom = (min(foot) - 2) if foot else page.height
        lines = page.crop((178, starts[0] - 3, page.width, bottom)).extract_text_lines()

    lines.sort(key=lambda l: l["top"])
    blocks, prev = [], None
    for l in lines:
        if prev is not None and l["top"] - prev["bottom"] <= 4:
            blocks[-1].append(l)
        else:
            blocks.append([l])
        prev = l

    zajecia = []
    for b in blocks:
        center = (b[0]["top"] + b[-1]["bottom"]) / 2
        day = max(i for i, s in enumerate(starts) if center >= s - 3) + 1
        for e in parse_block([l["text"] for l in b]):
            zajecia.append({"d": day, **e})
    if not zajecia:
        raise ValueError("Nie znaleziono żadnych zajęć")
    zajecia.sort(key=lambda z: (z["d"], z["s"]))

    plan = {"updated": "plan z wm.pollub.pl, pobrany " + datetime.date.today().isoformat(),
            "zajecia": zajecia}
    pathlib.Path(out_path).write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Zapisano {len(zajecia)} zajęć -> {out_path}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "data/plan.json")
