#!/usr/bin/env python3
"""Build a small pedal-notation gold-standard pilot from ASAP train/validation.

The script intentionally avoids the frozen ``test`` split and never writes into
``evals/C``.  It selects five diverse 4-measure windows with strong pedal-related
annotation signal, exports sliced performance MIDI, reference/system MusicXML and
SVG renderings, and writes an empty annotation CSV for a human reviewer.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import subprocess
import sys
from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
import xml.etree.ElementTree as ET

import pretty_midi

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "audio2score" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from asap_alignment import build_asap_alignment  # noqa: E402
from auto_label_candidates import build_auto_labeled_dataset  # noqa: E402
from auto_label_candidates import reference_score_events  # noqa: E402
from analyze_pedal_durations import build_records  # noqa: E402
from midi_to_score import detect_time_signature, midi_to_events, quantize_events  # noqa: E402
from score_metrics import pedal_events  # noqa: E402

EPS = 1e-7
DIVISORS = (8, 4, 3)
WINDOW_MARGIN_QL = 16.0  # 候选生成保留窗口前后各 4 小节上下文


@dataclass(frozen=True)
class Segment:
    row: dict
    start_measure: int
    end_measure: int
    score: float
    bar_ql: float
    time_sig: tuple[int, int]
    tempo_bpm: float

    @property
    def start_ql(self) -> float:
        return self.start_measure * self.bar_ql

    @property
    def end_ql(self) -> float:
        return (self.end_measure + 1) * self.bar_ql


def load_train_validation(manifest_path: Path) -> list[dict]:
    with manifest_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [row for row in rows if row["split"] in {"train", "validation"}]


def stratified_pool(rows: list[dict], per_composer: int, seed: int) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row["composer"]].append(row)
    rng = random.Random(seed)
    pool: list[dict] = []
    for group in groups.values():
        pool.extend(rng.sample(group, min(per_composer, len(group))))
    return pool


def _overlap_count(start_ql: float, end_ql: float, pedals: list[tuple[float, float]]) -> int:
    return sum(1 for start, end in pedals if end > start_ql + EPS and start < end_ql - EPS)


def _retake_count(start_ql: float, end_ql: float, pedals: list[tuple[float, float]]) -> int:
    count = 0
    for (left_start, left_end), (right_start, _right_end) in zip(pedals, pedals[1:]):
        if right_start < start_ql - EPS or right_start >= end_ql - EPS:
            continue
        if left_end <= right_start + EPS and right_start - left_end <= 0.25:
            count += 1
    return count


def _score_window(records, pedals, start_ql: float, end_ql: float) -> float:
    selected = [row for row in records if start_ql - EPS <= row.onset_ql < end_ql]
    if not selected:
        return -1.0
    extended = sum(row.pedal_extended_ql > 0.25 for row in selected)
    truncated = sum(row.truncated_by_current_single_voice for row in selected)
    retakes = _retake_count(start_ql, end_ql, pedals)
    note_count = len(selected)
    onset_groups: dict[tuple[str, float], int] = defaultdict(int)
    for row in selected:
        onset_groups[(row.hand, round(row.onset_ql, 6))] += 1
    chords = sum(1 for count in onset_groups.values() if count > 1)
    lh_sustain_with_rh_motion = 0
    lh = [row for row in selected if row.hand == "LH"]
    rh = [row for row in selected if row.hand == "RH"]
    for sustain in lh:
        if sustain.key_duration_ql < 1.5:
            continue
        overlapping_melody = sum(
            1 for row in rh
            if sustain.onset_ql <= row.onset_ql < sustain.onset_ql + sustain.key_duration_ql
        )
        if overlapping_melody >= 2:
            lh_sustain_with_rh_motion += 1
    signal = extended + retakes + truncated
    score = (
        4.0 * extended
        + 6.0 * retakes
        + 3.0 * truncated
        + 0.5 * min(note_count, 24)
        + 0.5 * chords
        + 2.0 * lh_sustain_with_rh_motion
        + 1.0 * _overlap_count(start_ql, end_ql, pedals)
    )
    if signal < 2:
        score *= 0.15
    return score


def analyze_performance(row: dict) -> tuple[list, list, tuple[int, int], float, float, float]:
    midi_path = ROOT / "data" / "ASAP" / row["midi_performance"]
    notes, pedals, meta = midi_to_events(str(midi_path))
    qnotes = quantize_events(notes, divisors=DIVISORS)
    time_sig = detect_time_signature(qnotes, meta["tempo_bpm"], meta["time_sigs"])
    if time_sig is None:
        time_sig = tuple(meta["time_sigs"][0][:2])
    bar_ql = 4.0 * time_sig[0] / time_sig[1]
    records = build_records(str(midi_path), divisors=DIVISORS)
    end = max((row.onset_ql + row.key_duration_ql for row in records), default=0.0)
    measure_count = max(1, math.ceil(end / bar_ql))
    return records, pedals, time_sig, bar_ql, measure_count, float(meta["tempo_bpm"])


def best_window(records, pedals, bar_ql: float, measure_count: int,
                window_len: int = 4) -> tuple[int, int, float] | None:
    best: tuple[int, int, float] | None = None
    for start_measure in range(max(0, measure_count - window_len + 1)):
        end_measure = start_measure + window_len - 1
        score = _score_window(
            records, pedals, start_measure * bar_ql, (end_measure + 1) * bar_ql
        )
        if score <= 0:
            continue
        if best is None or score > best[2]:
            best = (start_measure, end_measure, score)
    return best


def select_segments(rows: list[dict], count: int, seed: int) -> list[Segment]:
    candidates: list[Segment] = []
    pool = stratified_pool(rows, per_composer=6, seed=seed)
    for row in pool:
        try:
            records, pedals, time_sig, bar_ql, measure_count, tempo_bpm = analyze_performance(row)
            window = best_window(records, pedals, bar_ql, measure_count)
        except Exception:
            continue
        if window is None:
            continue
        start_measure, end_measure, score = window
        candidates.append(Segment(
            row=row,
            start_measure=start_measure,
            end_measure=end_measure,
            score=score,
            bar_ql=bar_ql,
            time_sig=time_sig,
            tempo_bpm=tempo_bpm,
        ))
    candidates.sort(key=lambda item: item.score, reverse=True)

    selected: list[Segment] = []
    used_pieces: set[str] = set()
    used_composers: set[str] = set()
    for candidate in candidates:
        piece = candidate.row["piece_key"]
        composer = candidate.row["composer"]
        if piece in used_pieces or composer in used_composers:
            continue
        selected.append(candidate)
        used_pieces.add(piece)
        used_composers.add(composer)
        if len(selected) == count:
            break
    if len(selected) < count:
        for candidate in candidates:
            if candidate in selected or candidate.row["piece_key"] in used_pieces:
                continue
            selected.append(candidate)
            used_pieces.add(candidate.row["piece_key"])
            if len(selected) == count:
                break
    return selected


def slice_midi(src: Path, dst: Path, start_ql: float, end_ql: float,
               pedals: list[tuple[float, float]]) -> None:
    source = pretty_midi.PrettyMIDI(str(src))
    tempos = source.get_tempo_changes()
    tempo_bpm = float(tempos[1][0])
    beat_sec = 60.0 / tempo_bpm
    start_sec = start_ql * beat_sec
    end_sec = end_ql * beat_sec
    output = pretty_midi.PrettyMIDI(resolution=source.resolution, initial_tempo=tempo_bpm)
    active_at_start = any(s - EPS <= start_ql < e - EPS for s, e in pedals)
    active_at_end = any(s - EPS <= end_ql < e - EPS for s, e in pedals)

    for instrument in source.instruments:
        out_inst = pretty_midi.Instrument(
            program=instrument.program,
            is_drum=instrument.is_drum,
            name=instrument.name,
        )
        for note in instrument.notes:
            if note.end > start_sec + EPS and note.start < end_sec - EPS:
                out_inst.notes.append(pretty_midi.Note(
                    velocity=note.velocity,
                    pitch=note.pitch,
                    start=max(note.start, start_sec) - start_sec,
                    end=min(note.end, end_sec) - start_sec,
                ))
        for cc in instrument.control_changes:
            if start_sec - EPS <= cc.time <= end_sec + EPS:
                out_inst.control_changes.append(pretty_midi.ControlChange(
                    number=cc.number,
                    value=cc.value,
                    time=max(cc.time, start_sec) - start_sec,
                ))
        if active_at_start:
            out_inst.control_changes.append(pretty_midi.ControlChange(number=64, value=127, time=0.0))
        if active_at_end:
            out_inst.control_changes.append(pretty_midi.ControlChange(
                number=64, value=0, time=end_sec - start_sec
            ))
        if out_inst.notes or out_inst.control_changes:
            output.instruments.append(out_inst)
    for ts in source.time_signature_changes:
        if start_sec - EPS <= ts.time <= end_sec + EPS:
            output.time_signature_changes.append(pretty_midi.TimeSignature(
                ts.numerator,
                ts.denominator,
                max(ts.time, start_sec) - start_sec,
            ))
    output.write(str(dst))


def _merge_attributes(measure: ET.Element, template: ET.Element | None) -> None:
    if template is None:
        return
    attrs = measure.find("attributes")
    if attrs is None:
        attrs = ET.Element("attributes")
        measure.insert(0, attrs)
    for child in template:
        if attrs.find(child.tag) is None:
            attrs.append(deepcopy(child))


def slice_musicxml(src: Path, dst: Path, start_measure: int, end_measure: int) -> None:
    tree = ET.parse(str(src))
    root = tree.getroot()
    output_root = ET.Element(root.tag, root.attrib)
    for child in root:
        if child.tag == "part":
            continue
        output_root.append(deepcopy(child))

    first_attributes: ET.Element | None = None
    for part in root.findall("part"):
        for measure in part.findall("measure"):
            attrs = measure.find("attributes")
            if attrs is not None:
                first_attributes = deepcopy(attrs)
                break
        if first_attributes is not None:
            break

    for part in root.findall("part"):
        measures = part.findall("measure")
        selected = measures[start_measure:end_measure + 1]
        new_part = ET.Element("part", part.attrib)
        for index, measure in enumerate(selected):
            copied = deepcopy(measure)
            if index == 0:
                _merge_attributes(copied, first_attributes)
            new_part.append(copied)
        output_root.append(new_part)
    dst.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(output_root).write(str(dst), encoding="UTF-8", xml_declaration=False)


def _fmt_beat(offset_ql: float, bar_ql: float) -> str:
    measure = int(math.floor(offset_ql / bar_ql)) + 1
    beat = (offset_ql % bar_ql) + 1.0
    return f"m.{measure} beat {beat:.3f}"


def write_event_files(segment: Segment, out_dir: Path, cand_rows: list[dict],
                      pedals: list[tuple[float, float]]) -> None:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in cand_rows:
        onset = float(row["onset_ql"])
        if segment.start_ql - EPS <= onset < segment.end_ql:
            grouped[row["candidate_event_id"]].append(row)

    event_fields = [
        "segment_id", "piece", "composer", "title", "event_id", "hand", "pitch",
        "onset_ql", "onset_location", "voice", "key_duration_ql", "acoustic_duration_ql",
        "pedal_extension_ql", "next_voice_gap_ql", "review_priority",
        "reference_part", "reference_voice", "reference_onset_ql",
        "reference_duration_ql", "reference_tie_start", "reference_tie_stop",
        "auto_label_status", "candidate_durations", "candidate_sources",
        "acoustic_sustain", "performance_pedal_action", "published_score_pedal",
        "notation_decision", "review_class", "review_note",
    ]
    with (out_dir / "events.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=event_fields)
        writer.writeheader()
        for event_id, rows in sorted(grouped.items()):
            first = rows[0]
            durations = sorted({round(float(row["candidate_duration_ql"]), 9) for row in rows})
            sources = sorted({row["candidate_source"] for row in rows})
            onset = float(first["onset_ql"])
            writer.writerow({
                "segment_id": out_dir.name,
                "piece": segment.row["piece_key"],
                "composer": segment.row["composer"],
                "title": segment.row["title"],
                "event_id": event_id,
                "hand": first["hand"],
                "pitch": first["pitch"],
                "onset_ql": f"{onset:.6f}",
                "onset_location": _fmt_beat(onset, segment.bar_ql),
                "voice": first["voice"],
                "key_duration_ql": first["key_duration_ql"],
                "acoustic_duration_ql": first["acoustic_duration_ql"],
                "pedal_extension_ql": first["pedal_extension_ql"],
                "next_voice_gap_ql": first["next_voice_gap_ql"],
                "review_priority": first["review_priority"],
                "reference_part": first["reference_part"],
                "reference_voice": first["reference_voice"],
                "reference_onset_ql": first["reference_onset_ql"],
                "reference_duration_ql": first["reference_duration_ql"],
                "reference_tie_start": first["reference_tie_start"],
                "reference_tie_stop": first["reference_tie_stop"],
                "auto_label_status": first["auto_label_status"],
                "candidate_durations": ";".join(f"{value:.6f}" for value in durations),
                "candidate_sources": ";".join(sources),
                "acoustic_sustain": "",
                "performance_pedal_action": "",
                "published_score_pedal": "",
                "notation_decision": "",
                "review_class": first.get("review_class", ""),
                "review_note": first.get("review_note", ""),
            })

    candidate_fields = list(cand_rows[0]) + [
        "acoustic_sustain", "performance_pedal_action", "published_score_pedal",
        "notation_decision",
    ]
    candidate_selected = [
        row for row in cand_rows
        if segment.start_ql - EPS <= float(row["onset_ql"]) < segment.end_ql
    ]
    with (out_dir / "candidate_options.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=candidate_fields, extrasaction="ignore")
        writer.writeheader()
        for row in candidate_selected:
            out = dict(row)
            out.update({
                "acoustic_sustain": "",
                "performance_pedal_action": "",
                "published_score_pedal": "",
                "notation_decision": "",
            })
            writer.writerow(out)

    with (out_dir / "pedal_intervals.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "interval_index", "start_ql", "end_ql", "start_location", "end_location",
            "clipped_start_ql", "clipped_end_ql", "retake_gap_ql",
        ])
        writer.writeheader()
        previous_end = None
        for index, (start, end) in enumerate(pedals, 1):
            if end <= segment.start_ql + EPS or start >= segment.end_ql - EPS:
                continue
            clipped_start = max(start, segment.start_ql)
            clipped_end = min(end, segment.end_ql)
            retake_gap = start - previous_end if previous_end is not None else ""
            writer.writerow({
                "interval_index": index,
                "start_ql": f"{start:.6f}",
                "end_ql": f"{end:.6f}",
                "start_location": _fmt_beat(start, segment.bar_ql),
                "end_location": _fmt_beat(end, segment.bar_ql),
                "clipped_start_ql": f"{clipped_start:.6f}",
                "clipped_end_ql": f"{clipped_end:.6f}",
                "retake_gap_ql": "" if retake_gap == "" else f"{retake_gap:.6f}",
            })
            previous_end = end


def write_reference_files(segment: Segment, out_dir: Path, xml_path: Path) -> None:
    events = reference_score_events(xml_path)
    selected = [
        event for event in events
        if segment.start_ql - EPS <= event.start_ql < segment.end_ql
    ]
    with (out_dir / "reference_events.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "hand", "pitch", "start_ql", "start_location", "duration_ql",
            "part_id", "voice", "tie_start", "tie_stop",
        ])
        writer.writeheader()
        for event in sorted(selected, key=lambda item: (item.hand, item.start_ql, item.pitch)):
            writer.writerow({
                "hand": event.hand,
                "pitch": event.pitch,
                "start_ql": f"{event.start_ql:.6f}",
                "start_location": _fmt_beat(event.start_ql, segment.bar_ql),
                "duration_ql": f"{event.duration_ql:.6f}",
                "part_id": event.part_id,
                "voice": event.voice,
                "tie_start": int(event.tie_start),
                "tie_stop": int(event.tie_stop),
            })

    pedals = pedal_events(xml_path)
    selected_pedals = [
        event for event in pedals
        if segment.start_ql - EPS <= event.position_ql < segment.end_ql
    ]
    with (out_dir / "reference_pedals.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["hand", "position_ql", "position_location", "event_type"])
        writer.writeheader()
        for event in selected_pedals:
            writer.writerow({
                "hand": event.hand,
                "position_ql": f"{event.position_ql:.6f}",
                "position_location": _fmt_beat(event.position_ql, segment.bar_ql),
                "event_type": event.event_type,
            })


def write_review_guide(out_dir: Path, segment: Segment, row: dict) -> None:
    text = f"""# Pedal Gold-Standard Pilot Segment

- Piece: {row['composer']} / {row['title']}
- Split: {row['split']}
- Performance: {row['midi_performance']}
- Measures: {segment.start_measure + 1}..{segment.end_measure + 1}
- Time signature: {segment.time_sig[0]}/{segment.time_sig[1]}

## Files

- `performance_segment.mid`: sliced performance MIDI used by the system.
- `events.csv`: one row per quantized performance event. Fill the final six columns.
- `candidate_options.csv`: candidate duration options generated by P4.
- `pedal_intervals.csv`: CC64 intervals overlapping this segment.
- `reference_events.csv`: published score notes in this measure range.
- `reference_pedals.csv`: published score pedal marks in this measure range.
- `p4_rule.svg`, `p4_learned.svg`, `p4_no_pedal.svg`: system renderings.
- `reference_score.svg`: published score slice.

## Annotation rules

1. `acoustic_sustain`: `yes` if the note would be acoustically sustained by CC64 or
   overlapping resonance; `no`; `uncertain`.
2. `performance_pedal_action`: the pedal action implied by CC64 at/near this event:
   `hold`, `change`, `release`, `none`, `uncertain`.
3. `published_score_pedal`: what the published MusicXML says at this event:
   `start`, `change`, `stop`, `none`, `uncertain`.
4. `notation_decision`: choose a candidate duration or write an explicit duration.
5. `review_class`: `independent-voice`, `notation-shortening`, `pedal-only`,
   `other`, or blank.
6. `review_note`: free text explaining the decision.

Do not force every acoustic sustain into a tie or long note. Prefer readable notation
and explicit reasoning.
"""
    (out_dir / "review_guide.md").write_text(text, encoding="utf-8")


def run_checked(cmd: list[str]) -> None:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed: {' '.join(cmd)}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )


def build_segment(segment: Segment, out_root: Path,
                    skip_align_if_present: bool = False,
                    skip_render: bool = False,
                    fuse_alpha: float | None = None,
                    pedal_placement: str = "snap") -> dict:
    row = segment.row
    performance = ROOT / "data" / "ASAP" / row["midi_performance"]
    reference_xml = ROOT / "data" / "ASAP" / row["xml_score"]
    reference_events_all = reference_score_events(reference_xml)
    reference_in_segment = [
        event for event in reference_events_all
        if segment.start_ql - EPS <= event.start_ql < segment.end_ql
    ]
    if len(reference_in_segment) < 10:
        raise RuntimeError(f"reference score covers too few events in segment: {len(reference_in_segment)}")
    segment_dir = out_root / f"{row['composer']}_{row['title']}_{segment.start_measure + 1}"
    segment_dir.mkdir(parents=True, exist_ok=True)
    work = segment_dir / "_work"
    work.mkdir(exist_ok=True)

    alignment = work / "alignment.csv"
    rejected = work / "rejected.csv"
    if skip_align_if_present and alignment.exists():
        align_stats = {"rows": max(0, sum(1 for _ in alignment.open(encoding="utf-8", newline="")) - 1)}
    else:
        align_stats = build_asap_alignment(
            ROOT / "data" / "ASAP",
            row["midi_performance"],
            alignment,
            rejected,
            divisors=DIVISORS,
        )
    if align_stats["rows"] < 10:
        raise RuntimeError(f"alignment too sparse: {align_stats['rows']} rows")

    candidates = work / "candidates.csv"
    candidate_stats = build_auto_labeled_dataset(
        str(performance),
        str(reference_xml),
        str(candidates),
        piece=row["piece_key"],
        alignment_path=str(alignment),
        divisors=DIVISORS,
        max_voices=12,
        bar_ql=segment.bar_ql,
        window=(segment.start_ql - WINDOW_MARGIN_QL, segment.end_ql + WINDOW_MARGIN_QL),
    )
    with candidates.open(encoding="utf-8", newline="") as handle:
        cand_rows = list(csv.DictReader(handle))
    if not cand_rows:
        raise RuntimeError("candidate dataset is empty")

    _notes, pedals, _meta = midi_to_events(str(performance))
    slice_midi(
        performance,
        segment_dir / "performance_segment.mid",
        segment.start_ql,
        segment.end_ql,
        pedals,
    )
    slice_musicxml(
        reference_xml,
        segment_dir / "reference_score.musicxml",
        segment.start_measure,
        segment.end_measure,
    )
    write_event_files(segment, segment_dir, cand_rows, pedals)
    write_reference_files(segment, segment_dir, reference_xml)
    write_review_guide(segment_dir, segment, row)

    model = str(ROOT / "audio2score" / "models" / "p4_asap_cross_piece_v1")
    commands = [
        ("p4_rule", ["--midi", str(segment_dir / "performance_segment.mid"),
                     "--out", str(segment_dir / "p4_rule.musicxml"),
                     "--max-voices", "12", "--divisors", "8,4,3"]),
        ("p4_learned", ["--midi", str(segment_dir / "performance_segment.mid"),
                        "--out", str(segment_dir / "p4_learned.musicxml"),
                        "--candidate-model", model,
                        "--max-voices", "12", "--divisors", "8,4,3"]),
        ("p4_no_pedal", ["--midi", str(segment_dir / "performance_segment.mid"),
                         "--out", str(segment_dir / "p4_no_pedal.musicxml"),
                         "--no-pedal",
                         "--max-voices", "12", "--divisors", "8,4,3"]),
    ]
    if fuse_alpha is not None:
        commands.append(
            ("p4_fused", ["--midi", str(segment_dir / "performance_segment.mid"),
                          "--out", str(segment_dir / "p4_fused.musicxml"),
                          "--candidate-model", model,
                          "--fuse-alpha", str(fuse_alpha),
                          "--max-voices", "12", "--divisors", "8,4,3"])
        )
    if pedal_placement == "exact":
        commands.append(
            ("p4_exact", ["--midi", str(segment_dir / "performance_segment.mid"),
                          "--out", str(segment_dir / "p4_exact.musicxml"),
                          "--pedal-placement", "exact",
                          "--max-voices", "12", "--divisors", "8,4,3"])
        )
    for stem, args in commands:
        run_checked([sys.executable, str(SCRIPTS / "p4_multivoice_score.py"), *args])
        if not skip_render:
            run_checked([
                sys.executable,
                str(SCRIPTS / "render_score.py"),
                "--musicxml", str(segment_dir / f"{stem}.musicxml"),
                "--out-svg", str(segment_dir / f"{stem}.svg"),
            ])
    if not skip_render:
        run_checked([
            sys.executable,
            str(SCRIPTS / "render_score.py"),
            "--musicxml", str(segment_dir / "reference_score.musicxml"),
            "--out-svg", str(segment_dir / "reference_score.svg"),
        ])
    
    metadata = {
        "segment_id": segment_dir.name,
        "manifest": row,
        "start_measure": segment.start_measure,
        "end_measure": segment.end_measure,
        "start_ql": segment.start_ql,
        "end_ql": segment.end_ql,
        "bar_ql": segment.bar_ql,
        "time_signature": list(segment.time_sig),
        "tempo_bpm": segment.tempo_bpm,
        "selection_score": segment.score,
        "alignment": align_stats,
        "candidate_stats": candidate_stats,
    }
    (segment_dir / "segment_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description="Build pedal gold-standard pilot")
    parser.add_argument("--manifest", default=str(ROOT / "data" / "asap_piece_manifest.csv"))
    parser.add_argument("--out", default=str(ROOT / "outputs" / "pedal_gold_standard" / "pilot"))
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260820)
    parser.add_argument("--max-attempts", type=int, default=20)
    parser.add_argument("--selection", default=None,
                        help="frozen selection JSON (from tools/select_gold_standard.py); "
                             "skips the expensive selection pass")
    args = parser.parse_args()

    if args.selection:
        payload = json.loads(Path(args.selection).read_text(encoding="utf-8"))
        segments = payload["segments"] if isinstance(payload, dict) else payload
        selected = [Segment(**item) for item in segments]
    else:
        rows = load_train_validation(Path(args.manifest))
        selected = select_segments(rows, args.count * 3, args.seed)
    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    built = []
    attempts = 0
    for segment in selected:
        if len(built) >= args.count:
            break
        try:
            built.append(build_segment(segment, out_root))
            print(f"[built] {built[-1]['segment_id']}")
        except Exception as exc:
            attempts += 1
            print(f"[skip] {segment.row['piece_key']}: {exc}", file=sys.stderr)
            if attempts >= args.max_attempts:
                break
    if not built:
        raise SystemExit("no segments could be built")
    summary = out_root / "selection_summary.json"
    summary.write_text(
        json.dumps({"segments": built}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[done] {len(built)} segments under {out_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
