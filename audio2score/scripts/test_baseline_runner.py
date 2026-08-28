#!/usr/bin/env python3
"""B 阶段统一基线运行器与汇总器的聚焦自动化测试。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from run_piece_baseline import warning_counts


class TestRenderWarningCounts(unittest.TestCase):
    def test_extracts_numeric_open_tie_count(self):
        stderr = "[Warning] MusicXML import: There are 6 ties left open\n"
        self.assertEqual(warning_counts(stderr)["ties_left_open"], 6)

    def test_counts_mixed_beam_line_once(self):
        stderr = (
            "[Warning] Insufficient space to draw mixed beam, starting at 'n1'. "
            "Drawing 'below' instead.\n"
        )
        warnings = warning_counts(stderr)
        self.assertEqual(warnings["beam_or_layout"], 1)
        self.assertEqual(warnings["ties_left_open"], 0)


class TestBaselineSummary(unittest.TestCase):
    @staticmethod
    def _write_metrics(path: Path, pipeline: str, acceptance_pass: bool) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "pipeline": pipeline,
            "status": "completed",
            "acceptance_pass": acceptance_pass,
            "reconciliation": {
                "input_event_count": 10,
                "xml_tie_merged_event_count": 10,
                "extra_count": 0,
                "missing_count": 0,
                "onset_drift_count": 0,
                "duration_drift_count": 0,
            },
            "render_qa": {
                "overfull_measure_count": 0,
                "tie_orphan_stop_count": 0,
                "tie_unclosed_start_count": 0,
                "tie_cross_voice_count": 0,
                "xml_parse_success": True,
                "render_success": True,
                "page_count": 1,
                "warnings": {"ties_left_open": 0, "beam_or_layout": 0},
            },
        }), encoding="utf-8")

    def test_summary_separates_completed_from_acceptance(self):
        scripts_dir = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pieces_dir = root / "pieces"
            self._write_metrics(pieces_dir / "piece-a" / "P3" / "metrics.json", "P3", False)
            self._write_metrics(pieces_dir / "piece-a" / "P4-R" / "metrics.json", "P4-R", True)
            out_dir = root / "summary"
            result = subprocess.run(
                [sys.executable, str(scripts_dir / "summarize_baselines.py"),
                 "--pieces-dir", str(pieces_dir), "--out-dir", str(out_dir)],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads((out_dir / "metrics_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["pipelines"]["P3"]["completed"], 1)
            self.assertEqual(summary["pipelines"]["P3"]["acceptance_passed"], 0)
            self.assertEqual(summary["pipelines"]["P4-R"]["completed"], 1)
            self.assertEqual(summary["pipelines"]["P4-R"]["acceptance_passed"], 1)
            markdown = (out_dir / "baseline_comparison.md").read_text(encoding="utf-8")
            self.assertIn("| P3 | 1 | 1/1 | 0/1 |", markdown)
            self.assertIn("| piece-a | P3 | completed | 未通过 |", markdown)


if __name__ == "__main__":
    unittest.main()
