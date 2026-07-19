"""
monitoring.py
Fetches Vertex AI Agent Engine runtime metrics from Cloud Monitoring.

Confirmed metric types (resource: aiplatform.googleapis.com/ReasoningEngine):
  - aiplatform.googleapis.com/reasoning_engine/request_count
  - aiplatform.googleapis.com/reasoning_engine/request_latencies
  - aiplatform.googleapis.com/reasoning_engine/container/cpu_allocation_time
  - aiplatform.googleapis.com/reasoning_engine/container/memory_allocation_time
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone
from google.cloud import monitoring_v3
from google.protobuf.timestamp_pb2 import Timestamp

log = logging.getLogger(__name__)

# ── Metric definitions ─────────────────────────────────────────────────────────
_METRICS = {
    "request_count": {
        "type":    "aiplatform.googleapis.com/reasoning_engine/request_count",
        "aligner": monitoring_v3.Aggregation.Aligner.ALIGN_DELTA,
        "reducer": monitoring_v3.Aggregation.Reducer.REDUCE_SUM,
    },
    "request_latencies": {
        "type":    "aiplatform.googleapis.com/reasoning_engine/request_latencies",
        "aligner": monitoring_v3.Aggregation.Aligner.ALIGN_DELTA,
        "reducer": monitoring_v3.Aggregation.Reducer.REDUCE_PERCENTILE_95,
        "is_distribution": True,
    },
    "cpu_allocation_time": {
        # Unit: seconds (CUMULATIVE → ALIGN_DELTA gives total seconds in the window)
        "type":    "aiplatform.googleapis.com/reasoning_engine/cpu/allocation_time",
        "aligner": monitoring_v3.Aggregation.Aligner.ALIGN_DELTA,
        "reducer": monitoring_v3.Aggregation.Reducer.REDUCE_SUM,
    },
    "memory_allocation_time": {
        # Unit: GB·seconds (CUMULATIVE → ALIGN_DELTA gives total GB-s in the window)
        "type":    "aiplatform.googleapis.com/reasoning_engine/memory/allocation_time",
        "aligner": monitoring_v3.Aggregation.Aligner.ALIGN_DELTA,
        "reducer": monitoring_v3.Aggregation.Reducer.REDUCE_SUM,
    },
}

# Alignment period: 1 hour buckets for charting
_ALIGNMENT_PERIOD_SECS = 3600


def _make_interval(start: datetime | str, end: datetime | str) -> monitoring_v3.TimeInterval:
    def _ts(dt: datetime | str) -> Timestamp:
        if isinstance(dt, str):
            # Parse standard ISO strings (with Z or offsets)
            try:
                dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            except Exception:
                # Fallback to basic formats if fromisoformat fails
                dt = datetime.strptime(dt, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        ts = Timestamp()
        ts.FromDatetime(dt.astimezone(timezone.utc))
        return ts

    return monitoring_v3.TimeInterval(
        {"start_time": _ts(start), "end_time": _ts(end)}
    )


def _query_metric(
    client: monitoring_v3.MetricServiceClient,
    project_name: str,
    engine_id: str,
    location: str,
    metric_key: str,
    start: datetime,
    end: datetime,
) -> list:
    """Run a single metric query and return raw TimeSeries objects."""
    meta = _METRICS[metric_key]
    filter_str = (
        f'metric.type="{meta["type"]}" '
        f'AND resource.labels.reasoning_engine_id="{engine_id}" '
        f'AND resource.labels.location="{location}"'
    )
    aggregation = monitoring_v3.Aggregation(
        {
            "alignment_period": {"seconds": _ALIGNMENT_PERIOD_SECS},
            "per_series_aligner": meta["aligner"],
            "cross_series_reducer": meta["reducer"],
            "group_by_fields": ["resource.labels.reasoning_engine_id"],
        }
    )
    try:
        results = client.list_time_series(
            request={
                "name":        project_name,
                "filter":      filter_str,
                "interval":    _make_interval(start, end),
                "view":        monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
                "aggregation": aggregation,
            }
        )
        return list(results)
    except Exception as exc:
        log.warning("Metric query failed [%s]: %s", metric_key, exc)
        return []


def _extract_scalar_sum(time_series_list: list) -> tuple[float, list[dict]]:
    """
    Sum all data-point values across all returned time series.
    Also return a list of {timestamp, value} for charting.
    """
    total = 0.0
    timeseries_points: list[dict] = []

    for ts in time_series_list:
        for point in ts.points:
            val = 0.0
            v = point.value
            # Use 'in' operator instead of HasField to safely check fields in proto-plus messages
            if "double_value" in v:
                val = v.double_value
            elif "int64_value" in v:
                val = float(v.int64_value)
            elif "distribution_value" in v:
                val = v.distribution_value.mean  # use mean for latency
            total += val
            dt_val = point.interval.end_time
            # In newer versions of the library, end_time is already a DatetimeWithNanoseconds object
            if hasattr(dt_val, "ToDatetime"):
                ts_val = dt_val.ToDatetime(tzinfo=timezone.utc)
            else:
                ts_val = dt_val.astimezone(timezone.utc)

            timeseries_points.append(
                {
                    "timestamp": ts_val,
                    "value":     val,
                }
            )

    # Sort oldest → newest
    timeseries_points.sort(key=lambda x: x["timestamp"])
    return total, timeseries_points


def get_agent_metrics(
    project_id: str,
    location: str,
    engine_id: str,
    start: datetime,
    end: datetime,
) -> dict:
    """
    Fetch all Agent Engine runtime metrics for one engine.

    Returns a dict with:
        request_count               – total requests in window
        p95_latency_ms              – P95 latency in milliseconds
        cpu_seconds                 – total vCPU-seconds allocated
        memory_gb_seconds           – total GiB-seconds allocated
        request_count_timeseries    – [{timestamp, value}]
        cpu_timeseries              – [{timestamp, value}]
        memory_timeseries           – [{timestamp, value}]
        latency_timeseries          – [{timestamp, value}]
    """
    client       = monitoring_v3.MetricServiceClient()
    project_name = f"projects/{project_id}"

    def _fetch(key):
        return _query_metric(client, project_name, engine_id, location, key, start, end)

    req_ts          = _fetch("request_count")
    lat_ts          = _fetch("request_latencies")
    cpu_ts          = _fetch("cpu_allocation_time")
    mem_ts          = _fetch("memory_allocation_time")

    req_total,  req_pts  = _extract_scalar_sum(req_ts)
    lat_total,  lat_pts  = _extract_scalar_sum(lat_ts)  # mean of P95 across buckets
    cpu_total,  cpu_pts  = _extract_scalar_sum(cpu_ts)
    mem_total,  mem_pts  = _extract_scalar_sum(mem_ts)

    # Latency is returned in milliseconds by Cloud Monitoring
    p95_latency_ms = lat_total  # already in ms per the metric definition

    return {
        "request_count":             req_total,
        "p95_latency_ms":            p95_latency_ms,
        "cpu_seconds":               cpu_total,
        "memory_gb_seconds":         mem_total,
        "request_count_timeseries":  req_pts,
        "latency_timeseries":        lat_pts,
        "cpu_timeseries":            cpu_pts,
        "memory_timeseries":         mem_pts,
    }


def get_metrics_for_agents(
    project_id: str,
    location: str,
    engine_ids: list[str],
    start: datetime,
    end: datetime,
) -> dict[str, dict]:
    """Fetch metrics for multiple engines. Returns {engine_id: metrics_dict}."""
    return {
        eid: get_agent_metrics(project_id, location, eid, start, end)
        for eid in engine_ids
    }