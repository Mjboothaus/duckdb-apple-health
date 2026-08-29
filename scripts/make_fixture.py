#!/usr/bin/env python3
"""Write synthetic Apple Health fixture files. No PHI. Stdlib only."""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "test" / "data"
GOLDEN = DATA / "golden"

# Fictional only.
LOCALE = "en_AU"
EXPORT_DATE = "2026-08-29 14:00:00 +1000"

RECORDS = [
    # quantity, Sydney offset
    {
        "type": "HKQuantityTypeIdentifierHeartRate",
        "unit": "count/min",
        "value": "72",
        "sourceName": "Demo Watch",
        "sourceVersion": "11.0",
        "device": "<<HKDevice: 0x0, name:Demo Watch, manufacturer:Apple Inc., model:Watch, hardware:Watch6,1, software:11.0>>",
        "creationDate": "2026-01-15 06:30:12 +1100",
        "startDate": "2026-01-15 06:30:00 +1100",
        "endDate": "2026-01-15 06:30:00 +1100",
    },
    {
        "type": "HKQuantityTypeIdentifierStepCount",
        "unit": "count",
        "value": "1234",
        "sourceName": "Demo Phone",
        "sourceVersion": "18.0",
        "device": "<<HKDevice: 0x0, name:Demo Phone, manufacturer:Apple Inc., model:iPhone, hardware:iPhone15,2, software:18.0>>",
        "creationDate": "2026-01-15 21:00:00 +1100",
        "startDate": "2026-01-15 08:00:00 +1100",
        "endDate": "2026-01-15 20:00:00 +1100",
    },
    # quantity, US Pacific
    {
        "type": "HKQuantityTypeIdentifierHeartRate",
        "unit": "count/min",
        "value": "118",
        "sourceName": "Demo Watch",
        "sourceVersion": "11.0",
        "device": "<<HKDevice: 0x0, name:Demo Watch, manufacturer:Apple Inc., model:Watch, hardware:Watch6,1, software:11.0>>",
        "creationDate": "2024-02-06 07:05:00 -0800",
        "startDate": "2024-02-06 07:00:00 -0800",
        "endDate": "2024-02-06 07:00:10 -0800",
    },
    # category (non-numeric value)
    {
        "type": "HKCategoryTypeIdentifierSleepAnalysis",
        "unit": None,
        "value": "HKCategoryValueSleepAnalysisAsleepCore",
        "sourceName": "Demo Watch",
        "sourceVersion": "11.0",
        "device": "<<HKDevice: 0x0, name:Demo Watch, manufacturer:Apple Inc., model:Watch, hardware:Watch6,1, software:11.0>>",
        "creationDate": "2026-01-15 07:00:00 +1100",
        "startDate": "2026-01-15 00:10:00 +1100",
        "endDate": "2026-01-15 01:40:00 +1100",
    },
    # non-ASCII source name
    {
        "type": "HKQuantityTypeIdentifierActiveEnergyBurned",
        "unit": "kcal",
        "value": "42.5",
        "sourceName": "Café Run Club",
        "sourceVersion": "3.2",
        "device": None,
        "creationDate": "2026-01-15 07:30:00 +1100",
        "startDate": "2026-01-15 07:00:00 +1100",
        "endDate": "2026-01-15 07:25:00 +1100",
    },
]

# Also appear as children of a Correlation and as top-level Records.
# Parser should emit top-level Record tags only (no double count).
BP_RECORDS = [
    {
        "type": "HKQuantityTypeIdentifierBloodPressureSystolic",
        "unit": "mmHg",
        "value": "118",
        "sourceName": "Demo Phone",
        "sourceVersion": "18.0",
        "device": None,
        "creationDate": "2026-01-14 08:00:00 +1100",
        "startDate": "2026-01-14 08:00:00 +1100",
        "endDate": "2026-01-14 08:00:00 +1100",
    },
    {
        "type": "HKQuantityTypeIdentifierBloodPressureDiastolic",
        "unit": "mmHg",
        "value": "76",
        "sourceName": "Demo Phone",
        "sourceVersion": "18.0",
        "device": None,
        "creationDate": "2026-01-14 08:00:00 +1100",
        "startDate": "2026-01-14 08:00:00 +1100",
        "endDate": "2026-01-14 08:00:00 +1100",
    },
]

WORKOUTS = [
    {
        "workoutActivityType": "HKWorkoutActivityTypeRunning",
        "duration": "25.0",
        "durationUnit": "min",
        "totalDistance": "4.2",
        "totalDistanceUnit": "km",
        "totalEnergyBurned": "280",
        "totalEnergyBurnedUnit": "kcal",
        "sourceName": "Demo Watch",
        "sourceVersion": "11.0",
        "device": "<<HKDevice: 0x0, name:Demo Watch>>",
        "creationDate": "2026-01-15 07:26:00 +1100",
        "startDate": "2026-01-15 07:00:00 +1100",
        "endDate": "2026-01-15 07:25:00 +1100",
    }
]

SUMMARIES = [
    # older export attrs
    {
        "dateComponents": "2020-06-01",
        "activeEnergyBurned": "410",
        "activeEnergyBurnedGoal": "500",
        "activeEnergyBurnedUnit": "kcal",
        "appleMoveMinutes": "32",
        "appleMoveMinutesGoal": "30",
        "appleExerciseTime": "28",
        "appleExerciseTimeGoal": "30",
        "appleStandHours": "10",
        "appleStandHoursGoal": "12",
    },
    # iOS 14+ attrs
    {
        "dateComponents": "2026-01-15",
        "activeEnergyBurned": "520",
        "activeEnergyBurnedGoal": "500",
        "activeEnergyBurnedUnit": "kcal",
        "appleMoveTime": "41",
        "appleMoveTimeGoal": "30",
        "appleExerciseTime": "35",
        "appleExerciseTimeGoal": "30",
        "appleStandHours": "11",
        "appleStandHoursGoal": "12",
    },
]


def _esc(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _attrs(d: dict[str, str | None]) -> str:
    parts = []
    for key, val in d.items():
        if val is None:
            continue
        parts.append(f'{key}="{_esc(val)}"')
    return " ".join(parts)


def _record_xml(rec: dict[str, str | None]) -> str:
    return f"  <Record {_attrs(rec)}/>"


def build_xml() -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<HealthData locale="en_AU">',
        f'  <ExportDate value="{EXPORT_DATE}"/>',
        '  <Me HKCharacteristicTypeIdentifierDateOfBirth="1990-01-15"',
        '     HKCharacteristicTypeIdentifierBiologicalSex="HKBiologicalSexNotSet"',
        '     HKCharacteristicTypeIdentifierBloodType="HKBloodTypeNotSet"',
        '     HKCharacteristicTypeIdentifierFitzpatrickSkinType="HKFitzpatrickSkinTypeNotSet"/>',
    ]
    for rec in RECORDS + BP_RECORDS:
        lines.append(_record_xml(rec))

    lines.append(
        '  <Correlation type="HKCorrelationTypeIdentifierBloodPressure" '
        'sourceName="Demo Phone" sourceVersion="18.0" '
        'creationDate="2026-01-14 08:00:00 +1100" '
        'startDate="2026-01-14 08:00:00 +1100" '
        'endDate="2026-01-14 08:00:00 +1100">'
    )
    for rec in BP_RECORDS:
        lines.append("  " + _record_xml(rec))
    lines.append("  </Correlation>")

    for w in WORKOUTS:
        lines.append(f'  <Workout {_attrs(w)}>')
        lines.append(
            '    <WorkoutEvent type="HKWorkoutEventTypePause" date="2026-01-15 07:10:00 +1100"/>'
        )
        lines.append(
            '    <WorkoutRoute sourceName="Demo Phone" sourceVersion="18.0" '
            'device="&lt;&lt;HKDevice: 0x0, name:Demo Phone&gt;&gt;" '
            'creationDate="2026-01-15 07:26:00 +1100" '
            'startDate="2026-01-15 07:00:00 +1100" '
            'endDate="2026-01-15 07:25:00 +1100">'
        )
        lines.append(
            '      <FileReference path="/workout-routes/route_2026-01-15_7.25am.gpx"/>'
        )
        lines.append("    </WorkoutRoute>")
        lines.append("  </Workout>")

    for s in SUMMARIES:
        lines.append(f"  <ActivitySummary {_attrs(s)}/>")

    lines.append("</HealthData>")
    lines.append("")
    return "\n".join(lines)


def _is_float(text: str) -> bool:
    try:
        float(text)
        return True
    except ValueError:
        return False


def _short(type_id: str) -> str:
    for prefix in (
        "HKQuantityTypeIdentifier",
        "HKCategoryTypeIdentifier",
        "HKCorrelationTypeIdentifier",
        "HKWorkoutActivityType",
        "HKDataType",
    ):
        if type_id.startswith(prefix):
            return type_id[len(prefix) :]
    return type_id


def write_golden_records(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "type",
        "type_short",
        "unit",
        "value",
        "value_text",
        "start_date",
        "end_date",
        "creation_date",
        "source_name",
        "source_version",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        # Explicit LF so fixtures match across macOS/Windows/Linux.
        writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        # Top-level records only (BP appears once, not via Correlation children).
        for rec in RECORDS + BP_RECORDS:
            raw = rec["value"] or ""
            numeric = _is_float(raw)
            writer.writerow(
                {
                    "type": rec["type"],
                    "type_short": _short(rec["type"]),
                    "unit": rec.get("unit") or "",
                    "value": raw if numeric else "",
                    "value_text": "" if numeric else raw,
                    "start_date": rec["startDate"],
                    "end_date": rec["endDate"],
                    "creation_date": rec["creationDate"],
                    "source_name": rec["sourceName"],
                    "source_version": rec["sourceVersion"],
                }
            )


DEMO_GPX = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<gpx version=\"1.1\" creator=\"apple_health_fixture\">\n  <trk>\n    <name>Demo Run</name>\n    <trkseg>\n      <trkpt lat=\"-33.8688\" lon=\"151.2093\"><ele>12.0</ele><time>2026-01-14T20:00:00Z</time></trkpt>\n      <trkpt lat=\"-33.8690\" lon=\"151.2100\"><ele>13.5</ele><time>2026-01-14T20:05:00Z</time></trkpt>\n      <trkpt lat=\"-33.8695\" lon=\"151.2110\"><ele>14.0</ele><time>2026-01-14T20:10:00Z</time></trkpt>\n    </trkseg>\n  </trk>\n</gpx>\n"""

def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    GOLDEN.mkdir(parents=True, exist_ok=True)

    xml = build_xml()
    xml_path = DATA / "export.xml"
    xml_path.write_text(xml, encoding="utf-8")

    zip_path = DATA / "export.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # Health app layout is typically apple_health_export/export.xml
        zf.writestr("apple_health_export/export.xml", xml)
        zf.writestr(
            "apple_health_export/workout-routes/route_2026-01-15_7.25am.gpx",
            DEMO_GPX,
        )

    write_golden_records(GOLDEN / "records.csv")

    print(f"wrote {xml_path.relative_to(ROOT)}")
    print(f"wrote {zip_path.relative_to(ROOT)}")
    print(f"wrote { (GOLDEN / 'records.csv').relative_to(ROOT) }")
    print(f"records (top-level): {len(RECORDS) + len(BP_RECORDS)}")
    print(f"workouts: {len(WORKOUTS)}")
    print("workout routes: 1")
    print(f"activity summaries: {len(SUMMARIES)}")


if __name__ == "__main__":
    main()
