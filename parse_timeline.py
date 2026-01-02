#!/usr/bin/env python3
"""
Parse the existing single-file HTML timeline and emit JSON.

Expected HTML structure (from your current file):
- div.month
  - h3 (e.g., "January 2025")
  - multiple div.event
    - h4 (title)
    - p  (description, may contain links)
    - span.tag + class names for access/modality/type

Outputs a JSON list of event objects.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from bs4 import BeautifulSoup


MONTHS = {
    "january": "01",
    "february": "02",
    "march": "03",
    "april": "04",
    "may": "05",
    "june": "06",
    "july": "07",
    "august": "08",
    "september": "09",
    "october": "10",
    "november": "11",
    "december": "12",
}

MODALITY_TAGS = {"text", "vision", "audio", "multimodal"}
TYPE_TAGS = {"model", "agent", "tool", "robot", "research", "partnership", "benchmark"}

ACCESS_CLASS_TO_VALUE = {
    "open-source": "open",   # your HTML uses "open-source" class for Open Weights :contentReference[oaicite:1]{index=1}
    "api-only": "api",
}


def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[’'“”]", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "event"


def unique_slug(base: str, used: Set[str]) -> str:
    if base not in used:
        used.add(base)
        return base
    i = 2
    while True:
        cand = f"{base}-{i}"
        if cand not in used:
            used.add(cand)
            return cand
        i += 1


def parse_month_key(h3_text: str) -> Optional[str]:
    """
    Convert "January 2025" -> "2025-01"
    """
    t = " ".join(h3_text.split()).strip()
    m = re.match(r"^([A-Za-z]+)\s+(\d{4})$", t)
    if not m:
        return None
    month_name = m.group(1).lower()
    year = m.group(2)
    mm = MONTHS.get(month_name)
    if not mm:
        return None
    return f"{year}-{mm}"


def extract_links(p_tag) -> Tuple[Optional[str], List[str]]:
    """
    Return (hf_link, other_links) from <p> content.
    """
    hf = None
    other: List[str] = []
    for a in p_tag.find_all("a"):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        if "huggingface.co" in href and hf is None:
            hf = href
        else:
            other.append(href)
    return hf, other


def extract_tag_classes(event_div) -> Set[str]:
    classes: Set[str] = set()
    for sp in event_div.select("span.tag"):
        for c in sp.get("class", []):
            if c != "tag":
                classes.add(c)
    return classes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("html", type=Path, help="Path to timeline HTML (e.g., index.html)")
    ap.add_argument("-o", "--out", type=Path, default=Path("events.2025.json"), help="Output JSON path")
    ap.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    args = ap.parse_args()

    html_text = args.html.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html_text, "html.parser")

    used_ids: Set[str] = set()
    events: List[Dict[str, Any]] = []

    month_divs = soup.select("div.month")
    if not month_divs:
        raise SystemExit("No div.month blocks found. Check the HTML structure/classes.")

    for month_div in month_divs:
        h3 = month_div.find("h3")
        if not h3:
            continue
        month_key = parse_month_key(h3.get_text(strip=True))
        if not month_key:
            # Skip unknown month headings
            continue

        for ev in month_div.select("div.event"):
            title_tag = ev.find("h4")
            desc_tag = ev.find("p")

            if not title_tag or not desc_tag:
                continue

            title = title_tag.get_text(" ", strip=True)
            desc = desc_tag.get_text(" ", strip=True)

            tag_classes = extract_tag_classes(ev)

            # access
            access = "unknown"
            for cls, value in ACCESS_CLASS_TO_VALUE.items():
                if cls in tag_classes:
                    access = value
                    break

            modalities = sorted([t for t in tag_classes if t in MODALITY_TAGS])
            types = sorted([t for t in tag_classes if t in TYPE_TAGS])

            hf, other_links = extract_links(desc_tag)

            event_id = unique_slug(slugify(title), used_ids)

            events.append(
                {
                    "id": event_id,
                    "month": month_key,     # e.g., "2025-01"
                    "date": None,           # unknown in current HTML; keep field for later
                    "name": title,
                    "desc": desc,
                    "access": access,       # "open" | "api" | "unknown"
                    "modalities": modalities,
                    "types": types,
                    "links": {
                        "hf": hf,
                        "other": other_links,
                    },
                    # You can extend later:
                    # "org": None,
                    # "tier": None,
                }
            )

    payload = {
        "schema": "ai-timeline-events.v1",
        "year": 2025,
        "count": len(events),
        "events": events,
    }

    if args.pretty:
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        args.out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    print(f"Wrote {len(events)} events → {args.out}")


if __name__ == "__main__":
    main()

