"""Optional Spark helper stats (extension point for future work)."""

from __future__ import annotations

from typing import Any, Dict, Optional


def collect_spark_stats(spark_stats_cmd: Optional[str], bench_id: str) -> Dict[str, Any]:
    """
    Hook for post-run Spark telemetry. Not implemented yet.

    When spark_stats_cmd is set, a future version may run it locally and parse output.
    """
    _ = spark_stats_cmd, bench_id
    return {}