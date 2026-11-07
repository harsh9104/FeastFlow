"""Dashboard metrics. Two interchangeable providers:

* ``local``       reads the per-minute rows written by ``metrics_collector`` (no AWS needed)
* ``cloudwatch``  reads CloudWatch / Auto Scaling / ELBv2 (used on AWS)

Select with METRICS_PROVIDER. Results are cached for METRICS_CACHE_TTL_S (default 30 s).
"""

import time
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from sqlalchemy import case, func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models.metrics import AppMetric

RANGES = {"15m": 900, "1h": 3600, "3h": 10800, "24h": 86400}
SERIES = {  # name -> unit
    "cpu_avg": "%",
    "mem_used_pct": "%",
    "request_count": "count",
    "target_response_time_p50": "s",
    "target_response_time_p90": "s",
    "http_5xx": "count",
    "healthy_hosts": "count",
    "unhealthy_hosts": "count",
    "in_service_instances": "count",
    "rds_cpu": "%",
    "rds_connections": "count",
}


def period_for(seconds: int) -> int:
    return 60 if seconds <= 3600 else 300 if seconds <= 10800 else 900


def _floor(ts: datetime, period: int) -> datetime:
    return datetime.fromtimestamp(int(ts.timestamp()) // period * period, tz=UTC)


def _envelope(provider: str, range_key: str, period: int, series: dict, unavailable: list) -> dict:
    return {
        "provider": provider,
        "range": range_key,
        "period_s": period,
        "series": series,
        "unavailable": unavailable,
    }


# --------------------------------------------------------------------------- local
class LocalProvider:
    name = "local"

    def _per_minute(self, db: Session, start: datetime, end: datetime | None = None) -> list[dict]:
        q = (
            select(
                AppMetric.minute,
                func.sum(AppMetric.request_count),
                func.sum(AppMetric.error_5xx),
                func.sum(AppMetric.p50_ms * AppMetric.request_count),
                func.sum(AppMetric.p90_ms * AppMetric.request_count),
                func.sum(case((AppMetric.p50_ms.is_not(None), AppMetric.request_count), else_=0)),
                func.avg(AppMetric.cpu_pct),
                func.avg(AppMetric.mem_pct),
                func.count(func.distinct(AppMetric.instance_id)),
            )
            .where(AppMetric.minute >= start)
            .group_by(AppMetric.minute)
            .order_by(AppMetric.minute)
        )
        if end:
            q = q.where(AppMetric.minute <= end)
        out = []
        for m, req, err, p50w, p90w, wt, cpu, mem, hosts in db.execute(q):
            out.append(
                {
                    "minute": m,
                    "req": int(req or 0),
                    "err": int(err or 0),
                    "p50": (p50w / wt / 1000) if wt else None,
                    "p90": (p90w / wt / 1000) if wt else None,
                    "weight": int(wt or 0),
                    "cpu": cpu,
                    "mem": mem,
                    "hosts": int(hosts or 0),
                }
            )
        return out

    def metrics(self, db: Session, range_key: str) -> dict:
        secs = RANGES[range_key]
        period = period_for(secs)
        end = _floor(datetime.now(UTC), period)
        start = end - timedelta(seconds=secs)
        grid = {start + timedelta(seconds=period * i): None for i in range(secs // period + 1)}
        acc: dict[datetime, dict] = {
            t: {
                "req": 0,
                "err": 0,
                "p50w": 0.0,
                "p90w": 0.0,
                "wt": 0,
                "cpu": [],
                "mem": [],
                "hosts": 0,
            }
            for t in grid
        }
        for r in self._per_minute(db, start):
            slot = acc.get(_floor(r["minute"], period))
            if slot is None:
                continue
            slot["req"] += r["req"]
            slot["err"] += r["err"]
            if r["p50"] is not None:
                slot["p50w"] += r["p50"] * r["weight"]
                slot["p90w"] += r["p90"] * r["weight"]
                slot["wt"] += r["weight"]
            if r["cpu"] is not None:
                slot["cpu"].append(r["cpu"])
            if r["mem"] is not None:
                slot["mem"].append(r["mem"])
            slot["hosts"] = max(slot["hosts"], r["hosts"])

        def avg(v: list) -> float | None:
            return round(sum(v) / len(v), 2) if v else None

        series: dict[str, list] = {k: [] for k in SERIES}
        conns = db.scalar(
            text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
        )
        for i, (t, s) in enumerate(acc.items()):
            iso = t.isoformat()
            has = bool(s["hosts"])
            series["cpu_avg"].append((iso, avg(s["cpu"])))
            series["mem_used_pct"].append((iso, avg(s["mem"])))
            series["request_count"].append((iso, s["req"]))
            series["http_5xx"].append((iso, s["err"]))
            series["target_response_time_p50"].append(
                (iso, round(s["p50w"] / s["wt"], 4) if s["wt"] else None)
            )
            series["target_response_time_p90"].append(
                (iso, round(s["p90w"] / s["wt"], 4) if s["wt"] else None)
            )
            series["healthy_hosts"].append((iso, s["hosts"] if has else None))
            series["unhealthy_hosts"].append((iso, 0 if has else None))
            series["in_service_instances"].append((iso, s["hosts"] if has else None))
            series["rds_cpu"].append((iso, None))
            series["rds_connections"].append((iso, int(conns) if i == len(acc) - 1 else None))
        return _envelope(
            "local",
            range_key,
            period,
            {
                k: {"unit": SERIES[k], "points": [{"t": t, "v": v} for t, v in pts]}
                for k, pts in series.items()
            },
            ["rds_cpu"],
        )

    def instances(self, db: Session) -> list[dict]:
        now = datetime.now(UTC)
        rows = db.execute(
            select(AppMetric.instance_id, func.min(AppMetric.minute), func.max(AppMetric.minute))
            .where(AppMetric.minute >= now - timedelta(hours=24))
            .group_by(AppMetric.instance_id)
        ).all()
        out = []
        for iid, first, last in rows:
            live = now - last <= timedelta(minutes=3)
            out.append(
                {
                    "instance_id": iid,
                    "az": "local",
                    "lifecycle_state": "InService" if live else "Offline",
                    "health_status": "Healthy" if live else "Unhealthy",
                    "target_health": "healthy" if live else "unused",
                    "launch_time": first.isoformat(),
                    "type": "container",
                }
            )
        return out

    def alarms(self, db: Session) -> list[dict]:
        now = datetime.now(UTC)
        last3 = self._per_minute(db, now - timedelta(minutes=4))[-3:]
        enough = len(last3) == 3

        def check(name: str, breach, label: str) -> dict:
            if not enough:
                state, reason = "INSUFFICIENT_DATA", "Fewer than 3 datapoints in the last 4 minutes"
            elif all(breach(r) for r in last3):
                state, reason = "ALARM", f"{label} breached for 3 consecutive minutes"
            else:
                state, reason = "OK", f"{label} within threshold"
            return {"name": name, "state": state, "reason": reason, "updated_at": now.isoformat()}

        return [
            check("feastflow-high-cpu", lambda r: (r["cpu"] or 0) > 75, "CPU > 75 %"),
            check("feastflow-high-memory", lambda r: (r["mem"] or 0) > 85, "Memory > 85 %"),
            check("feastflow-high-latency", lambda r: (r["p90"] or 0) > 1.0, "p90 latency > 1 s"),
            check(
                "feastflow-5xx-rate",
                lambda r: r["req"] > 0 and 100 * r["err"] / r["req"] > 5,
                "5xx rate > 5 %",
            ),
            check("feastflow-unhealthy-hosts", lambda r: False, "Unhealthy targets >= 1"),
            {
                "name": "feastflow-rds-cpu",
                "state": "INSUFFICIENT_DATA",
                "reason": "RDS metrics are not available with the local provider",
                "updated_at": now.isoformat(),
            },
        ]

    def scaling_activities(self, db: Session) -> list[dict]:
        return []  # single container: nothing scales locally

    def minutes(self, db: Session, start: datetime, end: datetime) -> dict[datetime, dict]:
        """Per-minute healthy hosts / requests / 5xx. Minutes without a report are absent."""
        rows = self._per_minute(db, start, end)
        return {r["minute"]: {"hosts": r["hosts"], "req": r["req"], "err": r["err"]} for r in rows}

    def usage(self, db: Session, start: datetime, end: datetime) -> dict:
        """Average in-service instances and total requests in the window (for cost estimates)."""
        rows = self._per_minute(db, start.replace(second=0, microsecond=0), end)
        hosts = [r["hosts"] for r in rows if r["hosts"]]
        if not hosts:
            return {"avg_instances": 1.0, "requests": 0, "source": "assumed"}
        return {
            "avg_instances": sum(hosts) / len(hosts),
            "requests": sum(r["req"] for r in rows),
            "source": "measured",
        }

    def window_summary(self, db: Session, start: datetime, end: datetime) -> dict:
        rows = self._per_minute(db, start.replace(second=0, microsecond=0), end)
        cpus = [r["cpu"] for r in rows if r["cpu"] is not None]
        mems = [r["mem"] for r in rows if r["mem"] is not None]
        hosts = [r["hosts"] for r in rows if r["hosts"]]
        return {
            "avg_cpu": round(sum(cpus) / len(cpus), 2) if cpus else None,
            "peak_cpu": round(max(cpus), 2) if cpus else None,
            "avg_mem": round(sum(mems) / len(mems), 2) if mems else None,
            "peak_mem": round(max(mems), 2) if mems else None,
            "min_instances": min(hosts) if hosts else None,
            "max_instances": max(hosts) if hosts else None,
        }


# --------------------------------------------------------------------------- CloudWatch
class CloudWatchProvider:
    """Reads real AWS data. Needs ASG_NAME, ALB_DIMENSION, TG_DIMENSION, TG_ARN, DB_INSTANCE_ID."""

    name = "cloudwatch"

    def __init__(self) -> None:
        import boto3

        s = get_settings()
        self.s = s
        self.cw = boto3.client("cloudwatch", region_name=s.aws_region)
        self.asg = boto3.client("autoscaling", region_name=s.aws_region)
        self.elb = boto3.client("elbv2", region_name=s.aws_region)
        self.ec2 = boto3.client("ec2", region_name=s.aws_region)

    # name -> (namespace, metric, dimensions, stat)
    def _queries(self) -> dict[str, tuple]:
        s = self.s
        asg = [{"Name": "AutoScalingGroupName", "Value": s.asg_name}]
        alb = [{"Name": "LoadBalancer", "Value": s.alb_dimension}]
        tg = [{"Name": "TargetGroup", "Value": s.tg_dimension}] + alb
        db = [{"Name": "DBInstanceIdentifier", "Value": s.db_instance_id}]
        e = "AWS/ApplicationELB"
        return {
            "cpu_avg": ("AWS/EC2", "CPUUtilization", asg, "Average"),
            "mem_used_pct": ("CWAgent", "mem_used_percent", asg, "Average"),
            "request_count": (e, "RequestCount", alb, "Sum"),
            "target_response_time_p50": (e, "TargetResponseTime", alb, "p50"),
            "target_response_time_p90": (e, "TargetResponseTime", alb, "p90"),
            "http_5xx": (e, "HTTPCode_Target_5XX_Count", alb, "Sum"),
            "healthy_hosts": (e, "HealthyHostCount", tg, "Average"),
            "unhealthy_hosts": (e, "UnHealthyHostCount", tg, "Average"),
            "in_service_instances": ("AWS/AutoScaling", "GroupInServiceInstances", asg, "Average"),
            "rds_cpu": ("AWS/RDS", "CPUUtilization", db, "Average"),
            "rds_connections": ("AWS/RDS", "DatabaseConnections", db, "Average"),
        }

    def _get(self, queries: dict[str, tuple], start: datetime, end: datetime, period: int) -> dict:
        ids = {f"q{i}": name for i, name in enumerate(queries)}
        data = [
            {
                "Id": qid,
                "MetricStat": {
                    "Metric": {"Namespace": ns, "MetricName": metric, "Dimensions": dims},
                    "Period": period,
                    "Stat": stat,
                },
                "ReturnData": True,
            }
            for qid, (ns, metric, dims, stat) in zip(ids, queries.values(), strict=True)
        ]
        out: dict[str, list] = {name: [] for name in queries}
        token = None
        while True:
            kw = {
                "MetricDataQueries": data,
                "StartTime": start,
                "EndTime": end,
                "ScanBy": "TimestampAscending",
            }
            if token:
                kw["NextToken"] = token
            resp = self.cw.get_metric_data(**kw)
            for r in resp["MetricDataResults"]:
                out[ids[r["Id"]]].extend(zip(r["Timestamps"], r["Values"], strict=True))
            token = resp.get("NextToken")
            if not token:
                return out

    def metrics(self, db: Session, range_key: str) -> dict:
        secs = RANGES[range_key]
        period = period_for(secs)
        end = datetime.now(UTC)
        raw = self._get(self._queries(), end - timedelta(seconds=secs), end, period)
        series = {}
        for name, pts in raw.items():
            series[name] = {
                "unit": SERIES[name],
                "points": [{"t": t.isoformat(), "v": round(v, 4)} for t, v in sorted(pts)],
            }
        return _envelope("cloudwatch", range_key, period, series, [])

    def instances(self, db: Session) -> list[dict]:
        groups = self.asg.describe_auto_scaling_groups(AutoScalingGroupNames=[self.s.asg_name])
        members = groups["AutoScalingGroups"][0]["Instances"] if groups["AutoScalingGroups"] else []
        tgh = {}
        if self.s.tg_arn:
            r = self.elb.describe_target_health(TargetGroupArn=self.s.tg_arn)
            tgh = {
                t["Target"]["Id"]: t["TargetHealth"]["State"] for t in r["TargetHealthDescriptions"]
            }
        launch = {}
        if members:
            res = self.ec2.describe_instances(InstanceIds=[m["InstanceId"] for m in members])
            for resv in res["Reservations"]:
                for i in resv["Instances"]:
                    launch[i["InstanceId"]] = i["LaunchTime"].isoformat()
        return [
            {
                "instance_id": m["InstanceId"],
                "az": m["AvailabilityZone"],
                "lifecycle_state": m["LifecycleState"],
                "health_status": m["HealthStatus"],
                "target_health": tgh.get(m["InstanceId"], "unknown"),
                "launch_time": launch.get(m["InstanceId"]),
                "type": m.get("InstanceType", "t3.micro"),
            }
            for m in members
        ]

    def alarms(self, db: Session) -> list[dict]:
        r = self.cw.describe_alarms(AlarmNamePrefix="feastflow-")
        return [
            {
                "name": a["AlarmName"],
                "state": a["StateValue"],
                "reason": a.get("StateReason", ""),
                "updated_at": a["StateUpdatedTimestamp"].isoformat(),
            }
            for a in r["MetricAlarms"]
        ]

    def scaling_activities(self, db: Session) -> list[dict]:
        r = self.asg.describe_scaling_activities(
            AutoScalingGroupName=self.s.asg_name, MaxRecords=20
        )
        return [
            {
                "start_time": a["StartTime"].isoformat(),
                "end_time": a["EndTime"].isoformat() if a.get("EndTime") else None,
                "status": a["StatusCode"],
                "description": a.get("Description", ""),
                "cause": a.get("Cause", ""),
            }
            for a in r["Activities"]
        ]

    def minutes(self, db: Session, start: datetime, end: datetime) -> dict[datetime, dict]:
        s = self.s
        alb = [{"Name": "LoadBalancer", "Value": s.alb_dimension}]
        tg = [{"Name": "TargetGroup", "Value": s.tg_dimension}] + alb
        e = "AWS/ApplicationELB"
        qs = {
            "hosts": (e, "HealthyHostCount", tg, "Minimum"),
            "req": (e, "RequestCount", alb, "Sum"),
            "tgt5xx": (e, "HTTPCode_Target_5XX_Count", alb, "Sum"),
            "elb5xx": (e, "HTTPCode_ELB_5XX_Count", alb, "Sum"),
        }
        raw = self._get(qs, start, end + timedelta(minutes=1), 60)
        out: dict[datetime, dict] = {}
        for t, v in raw["hosts"]:  # a minute exists only if HealthyHostCount was reported
            out[t.replace(second=0, microsecond=0)] = {"hosts": int(v), "req": 0, "err": 0}
        for key, field in (("req", "req"), ("tgt5xx", "err"), ("elb5xx", "err")):
            for t, v in raw[key]:
                slot = out.get(t.replace(second=0, microsecond=0))
                if slot is not None:
                    slot[field] += int(v)
        return out

    def usage(self, db: Session, start: datetime, end: datetime) -> dict:
        asg = [{"Name": "AutoScalingGroupName", "Value": self.s.asg_name}]
        alb = [{"Name": "LoadBalancer", "Value": self.s.alb_dimension}]
        qs = {
            "inst": ("AWS/AutoScaling", "GroupInServiceInstances", asg, "Average"),
            "req": ("AWS/ApplicationELB", "RequestCount", alb, "Sum"),
        }
        raw = self._get(qs, start, end + timedelta(minutes=1), 60)
        inst = [v for _, v in raw["inst"]]
        return {
            "avg_instances": sum(inst) / len(inst) if inst else 2.0,
            "requests": int(sum(v for _, v in raw["req"])),
            "source": "measured" if inst else "assumed",
        }

    def window_summary(self, db: Session, start: datetime, end: datetime) -> dict:
        s = self.s
        asg = [{"Name": "AutoScalingGroupName", "Value": s.asg_name}]
        qs = {
            "avg_cpu": ("AWS/EC2", "CPUUtilization", asg, "Average"),
            "peak_cpu": ("AWS/EC2", "CPUUtilization", asg, "Maximum"),
            "avg_mem": ("CWAgent", "mem_used_percent", asg, "Average"),
            "peak_mem": ("CWAgent", "mem_used_percent", asg, "Maximum"),
            "min_instances": ("AWS/AutoScaling", "GroupInServiceInstances", asg, "Minimum"),
            "max_instances": ("AWS/AutoScaling", "GroupInServiceInstances", asg, "Maximum"),
        }
        raw = self._get(qs, start, end + timedelta(minutes=1), 60)

        def vals(k: str) -> list[float]:
            return [v for _, v in raw[k]]

        def mean(k: str):
            v = vals(k)
            return round(sum(v) / len(v), 2) if v else None

        def top(k: str, f):
            v = vals(k)
            return round(f(v), 2) if v else None

        return {
            "avg_cpu": mean("avg_cpu"),
            "peak_cpu": top("peak_cpu", max),
            "avg_mem": mean("avg_mem"),
            "peak_mem": top("peak_mem", max),
            "min_instances": int(top("min_instances", min)) if vals("min_instances") else None,
            "max_instances": int(top("max_instances", max)) if vals("max_instances") else None,
        }


# --------------------------------------------------------------------------- facade
@lru_cache
def get_provider():
    return (
        CloudWatchProvider() if get_settings().metrics_provider == "cloudwatch" else LocalProvider()
    )


_cache: dict[tuple, tuple[float, dict]] = {}


def clear_cache() -> None:
    _cache.clear()


def get_metrics(db: Session, range_key: str) -> dict:
    if range_key not in RANGES:
        raise AppError(422, "INVALID_RANGE", f"range must be one of {', '.join(RANGES)}")
    provider = get_provider()
    ttl = get_settings().metrics_cache_ttl_s
    key = (provider.name, range_key)
    hit = _cache.get(key)
    if ttl and hit and hit[0] > time.time():
        return hit[1]
    data = provider.metrics(db, range_key)
    if ttl:
        _cache[key] = (time.time() + ttl, data)
    return data


def safe_window_summary(db: Session, start: datetime, end: datetime) -> dict:
    """Never let a metrics problem break finalizing a load-test run."""
    try:
        return get_provider().window_summary(db, start, end)
    except Exception:
        return {}
