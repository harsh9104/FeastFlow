"""Cloud & Cost panel: what is running on AWS right now and what it costs.

Reads the Auto Scaling Group (instances, scaling policy, activity history), CloudWatch
(CPU and in-service instances for the last hour, the feastflow alarms), RDS / Locust state and
the AWS Budget, then estimates the hourly bill from list prices.

Each section is read on its own: if the lab denies one call, that section carries an
`error` and the rest of the panel still works. Results are cached per process for
`cloud_cache_seconds` so admin tabs polling the panel don't hammer the AWS APIs.
"""

import logging
import threading
import time
from datetime import UTC, datetime, timedelta

from botocore.exceptions import BotoCoreError, ClientError

from app.core import aws
from app.core.config import get_settings
from app.core.instance import instance_id

log = logging.getLogger(__name__)

# us-east-1 on-demand list prices, USD per hour (Nov 2026).
PRICE = {
    "t3.micro": 0.0104,
    "t3.small": 0.0208,
    "alb": 0.0225,  # fixed hourly charge; LCUs are tiny at demo traffic
    "rds_db.t3.micro": 0.017,
    "rds_storage_gb_month": 0.115,  # gp2, charged even while the database is stopped
    "public_ipv4": 0.005,
}
RDS_STORAGE_GB = 20
HOURS_PER_MONTH = 730
RUNNING_INSTANCE_STATES = ("Pending", "InService", "Pending:Wait", "Pending:Proceed")

_lock = threading.Lock()
_cache: dict = {"at": 0.0, "data": None}


def clear_cache() -> None:
    _cache.update(at=0.0, data=None)


def overview() -> dict:
    s = get_settings()
    if not s.asg_name:
        return {"configured": False, "served_by": instance_id()}
    with _lock:
        if _cache["data"] is not None and time.monotonic() - _cache["at"] < s.cloud_cache_seconds:
            return _cache["data"]
        data = _build()
        _cache.update(at=time.monotonic(), data=data)
        return data


def _section(fn, *args):
    """Run one reader; AWS errors become {"error": ...} so other sections still show."""
    try:
        return fn(*args)
    except ClientError as e:
        err = e.response.get("Error", {})
        log.warning("cloud panel: %s failed: %s", fn.__name__, err.get("Code"))
        return {"error": f"{err.get('Code', 'Error')}: {err.get('Message', '')}".strip()}
    except BotoCoreError as e:
        log.warning("cloud panel: %s failed: %s", fn.__name__, e)
        return {"error": str(e)}


def _build() -> dict:
    s = get_settings()
    asg = _section(_asg, s.asg_name)
    resources = {
        "rds": _section(_rds, s.rds_instance_id) if s.rds_instance_id else None,
        "locust": _section(_locust, s.locust_instance_id) if s.locust_instance_id else None,
        "alb": _section(_alb, s.alb_name) if s.alb_name else None,
    }
    return {
        "configured": True,
        "served_by": instance_id(),
        "fetched_at": _iso(datetime.now(UTC)),
        "asg": asg,
        "metrics": _section(_metrics, s.asg_name),
        "activities": _section(_activities, s.asg_name),
        "alarms": _section(_alarms),
        "resources": resources,
        "cost": _cost(asg, resources),
        "budget": _section(_budget, s.budget_name) if s.budget_name else None,
    }


def _iso(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).isoformat() if dt else None


# ---- readers ------------------------------------------------------------------


def _asg(name: str) -> dict:
    autoscaling = aws.service("autoscaling")
    groups = autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[name])
    if not groups["AutoScalingGroups"]:
        return {"error": f"Auto Scaling Group {name} not found"}
    g = groups["AutoScalingGroups"][0]
    instances = [
        {
            "id": i["InstanceId"],
            "az": i.get("AvailabilityZone"),
            "type": i.get("InstanceType"),
            "lifecycle": i.get("LifecycleState"),
            "health": i.get("HealthStatus"),
            "launched_at": None,
        }
        for i in g.get("Instances", [])
    ]
    if instances:
        reservations = aws.service("ec2").describe_instances(
            InstanceIds=[i["id"] for i in instances]
        )["Reservations"]
        launched = {
            inst["InstanceId"]: _iso(inst.get("LaunchTime"))
            for r in reservations
            for inst in r["Instances"]
        }
        for i in instances:
            i["launched_at"] = launched.get(i["id"])
    instances.sort(key=lambda i: i["launched_at"] or "")

    cpu_target = None
    for p in autoscaling.describe_policies(AutoScalingGroupName=name).get("ScalingPolicies", []):
        cfg = p.get("TargetTrackingConfiguration")
        if cfg:
            cpu_target = cfg.get("TargetValue")
    return {
        "name": name,
        "min": g["MinSize"],
        "max": g["MaxSize"],
        "desired": g["DesiredCapacity"],
        "cpu_target": cpu_target,
        "instances": instances,
    }


def _metrics(asg_name: str) -> dict:
    """Last hour, one point per minute (the launch template enables detailed monitoring)."""
    end = datetime.now(UTC)
    res = aws.service("cloudwatch").get_metric_data(
        StartTime=end - timedelta(hours=1),
        EndTime=end,
        ScanBy="TimestampAscending",
        MetricDataQueries=[
            {
                "Id": "cpu",
                "MetricStat": {
                    "Metric": {
                        "Namespace": "AWS/EC2",
                        "MetricName": "CPUUtilization",
                        "Dimensions": [{"Name": "AutoScalingGroupName", "Value": asg_name}],
                    },
                    "Period": 60,
                    "Stat": "Average",
                },
            },
            {
                "Id": "instances",
                "MetricStat": {
                    "Metric": {
                        "Namespace": "AWS/AutoScaling",
                        "MetricName": "GroupInServiceInstances",
                        "Dimensions": [{"Name": "AutoScalingGroupName", "Value": asg_name}],
                    },
                    "Period": 60,
                    "Stat": "Maximum",
                },
            },
        ],
    )
    series = {}
    for r in res.get("MetricDataResults", []):
        pairs = sorted(zip(r.get("Timestamps", []), r.get("Values", []), strict=False))
        series[r["Id"]] = [{"t": _iso(t), "v": round(v, 1)} for t, v in pairs]
    return {"cpu": series.get("cpu", []), "instances": series.get("instances", [])}


def _activities(asg_name: str) -> dict:
    res = aws.service("autoscaling").describe_scaling_activities(
        AutoScalingGroupName=asg_name, MaxRecords=10
    )
    return {
        "items": [
            {
                "at": _iso(a.get("StartTime")),
                "description": a.get("Description", ""),
                "status": a.get("StatusCode", ""),
                "cause": a.get("Cause", ""),
            }
            for a in res.get("Activities", [])
        ]
    }


def _alarms() -> dict:
    """The project's alarms plus the ones the CPU target-tracking policy created."""
    cw = aws.service("cloudwatch")
    found = []
    for prefix in ("feastflow-", "TargetTracking-feastflow"):
        found += cw.describe_alarms(AlarmNamePrefix=prefix, MaxRecords=100).get("MetricAlarms", [])
    order = {"ALARM": 0, "INSUFFICIENT_DATA": 1, "OK": 2}
    items = [
        {
            "name": a["AlarmName"],
            "state": a.get("StateValue", "INSUFFICIENT_DATA"),
            "reason": a.get("StateReason", ""),
            "since": _iso(a.get("StateUpdatedTimestamp")),
            "scaling": a["AlarmName"].startswith("TargetTracking-"),
        }
        for a in found
    ]
    items.sort(key=lambda a: (order.get(a["state"], 3), a["scaling"], a["name"]))
    return {"items": items}


def _rds(db_id: str) -> dict:
    db = aws.service("rds").describe_db_instances(DBInstanceIdentifier=db_id)["DBInstances"][0]
    return {
        "id": db_id,
        "status": db.get("DBInstanceStatus"),
        "class": db.get("DBInstanceClass"),
        "storage_gb": db.get("AllocatedStorage", RDS_STORAGE_GB),
    }


def _locust(locust_id: str) -> dict:
    r = aws.service("ec2").describe_instances(InstanceIds=[locust_id])["Reservations"]
    inst = r[0]["Instances"][0]
    return {
        "id": locust_id,
        "status": inst["State"]["Name"],
        "type": inst.get("InstanceType"),
        "public_ip": bool(inst.get("PublicIpAddress")),
    }


def _alb(alb_name: str) -> dict:
    lb = aws.service("elbv2").describe_load_balancers(Names=[alb_name])["LoadBalancers"][0]
    return {
        "name": alb_name,
        "status": lb.get("State", {}).get("Code"),
        "zones": len(lb.get("AvailabilityZones", [])),
    }


def _budget(budget_name: str) -> dict:
    account = aws.service("sts").get_caller_identity()["Account"]
    b = aws.service("budgets").describe_budget(AccountId=account, BudgetName=budget_name)["Budget"]

    def amount(d: dict | None) -> float | None:
        return round(float(d["Amount"]), 2) if d and d.get("Amount") is not None else None

    spend = b.get("CalculatedSpend", {})
    return {
        "name": budget_name,
        "limit": amount(b.get("BudgetLimit")),
        "actual": amount(spend.get("ActualSpend")),
        "forecast": amount(spend.get("ForecastedSpend")),
    }


# ---- cost estimate ------------------------------------------------------------


def _ok(section) -> bool:
    return isinstance(section, dict) and "error" not in section


def _cost(asg: dict, resources: dict) -> dict:
    """Hourly estimate from what is running now. Sections that failed to load are skipped
    and listed in `unknown`, so the total is a lower bound in that case."""
    lines, unknown = [], []

    def add(item, qty, unit, note=""):
        lines.append(
            {
                "item": item,
                "qty": qty,
                "unit_per_hour": unit,
                "per_hour": round(qty * unit, 4),
                "note": note,
            }
        )

    ipv4 = 0
    if _ok(asg):
        running = [i for i in asg["instances"] if i["lifecycle"] in RUNNING_INSTANCE_STATES]
        by_type: dict[str, int] = {}
        for i in running:
            by_type[i["type"] or "t3.micro"] = by_type.get(i["type"] or "t3.micro", 0) + 1
        for itype, n in sorted(by_type.items()):
            add(
                f"App servers ({itype})",
                n,
                PRICE.get(itype, PRICE["t3.micro"]),
                "Auto Scaling Group, changes with load",
            )
        if not running:
            add("App servers (t3.micro)", 0, PRICE["t3.micro"], "ASG scaled to 0")
        ipv4 += len(running)
    else:
        unknown.append("app servers")

    alb = resources.get("alb")
    if alb is None or _ok(alb):
        add("Application Load Balancer", 1, PRICE["alb"], "always on while deployed")
        ipv4 += alb["zones"] if alb else 2
    else:
        unknown.append("load balancer")

    rds = resources.get("rds")
    if rds is not None:
        if _ok(rds):
            on = rds["status"] not in ("stopped", "stopping")
            add(
                f"RDS MySQL ({rds['class'] or 'db.t3.micro'})",
                1 if on else 0,
                PRICE["rds_db.t3.micro"],
                rds["status"] or "",
            )
            gb = rds["storage_gb"] or RDS_STORAGE_GB
            add(
                f"RDS storage ({gb} GB)",
                gb,
                PRICE["rds_storage_gb_month"] / HOURS_PER_MONTH,
                "charged even when stopped",
            )
        else:
            unknown.append("database")

    locust = resources.get("locust")
    if locust is not None:
        if _ok(locust):
            on = locust["status"] in ("pending", "running")
            add(
                f"Locust load generator ({locust['type'] or 't3.small'})",
                1 if on else 0,
                PRICE.get(locust["type"] or "t3.small", PRICE["t3.small"]),
                locust["status"],
            )
            ipv4 += 1 if on and locust["public_ip"] else 0
        else:
            unknown.append("load generator")

    add("Public IPv4 addresses", ipv4, PRICE["public_ipv4"], "servers + load balancer")
    per_hour = round(sum(line["per_hour"] for line in lines), 4)
    return {
        "lines": lines,
        "per_hour": per_hour,
        "per_day": round(per_hour * 24, 2),
        "per_month": round(per_hour * HOURS_PER_MONTH, 2),
        "unknown": unknown,
        "note": "List-price estimate. SQS, SNS, S3, Lambda and CloudWatch cost about $0 "
        "at this volume.",
    }
