"""AWS cost estimates = published on-demand rates x measured usage (Cost Explorer is unavailable
in the Learner Lab, assumption A-06). Usage comes from the active metrics provider."""

import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.order import Order
from app.services import metrics_service

RATE_TABLE: dict = json.loads(
    (Path(__file__).parent.parent / "config" / "aws_rates.json").read_text(encoding="utf-8")
)


def _item(service: str, usage: float, unit: str, rate: float) -> dict:
    return {
        "service": service,
        "usage": round(usage, 6),
        "unit": unit,
        "rate_usd": rate,
        "cost_usd": round(usage * rate, 6),
    }


def estimate(db: Session, start: datetime, end: datetime, requests: int | None = None) -> dict:
    """Cost of running the whole stack during [start, end]."""
    r, a = RATE_TABLE["rates"], RATE_TABLE["assumptions"]
    seconds = max((end - start).total_seconds(), 1.0)
    hours = seconds / 3600
    usage = metrics_service.get_provider().usage(db, start, end)
    req = requests if requests is not None else usage["requests"]
    app_hours = usage["avg_instances"] * hours
    avg_rps = req / seconds
    lcu = a["lcu_base"] + avg_rps / a["rps_per_extra_lcu"]
    month = a["hours_per_month"]

    items = [
        _item("EC2 t3.micro (app instances)", app_hours, "instance-hours", r["ec2_t3_micro_hour"]),
        _item("EC2 t3.small (Locust)", hours, "instance-hours", r["ec2_t3_small_hour"]),
        _item("Application Load Balancer", hours, "hours", r["alb_hour"]),
        _item("ALB capacity units (LCU)", lcu * hours, "LCU-hours", r["alb_lcu_hour"]),
        _item("RDS db.t3.micro", hours, "instance-hours", r["rds_t3_micro_hour"]),
        _item(
            "RDS storage (gp3)",
            a["rds_storage_gb"] * hours / month,
            "GB-months",
            r["rds_gp3_gb_month"],
        ),
        _item(
            "EBS volumes (gp3)",
            a["app_ebs_gb"] * app_hours / month + a["locust_ebs_gb"] * hours / month,
            "GB-months",
            r["ebs_gp3_gb_month"],
        ),
        _item(
            "Public IPv4 addresses",
            app_hours + hours + a["alb_nodes"] * hours,
            "address-hours",
            r["public_ipv4_hour"],
        ),
        _item("CloudWatch (flat estimate)", hours, "hours", r["cloudwatch_flat_hour"]),
    ]
    total = round(sum(i["cost_usd"] for i in items), 4)
    orders = db.scalar(
        select(func.count()).select_from(Order).where(Order.created_at.between(start, end))
    )
    return {
        "period": {"from": start.isoformat(), "to": end.isoformat(), "hours": round(hours, 4)},
        "provider": metrics_service.get_provider().name,
        "line_items": items,
        "total_usd": total,
        "requests": req,
        "orders": orders,
        "cost_per_1000_orders_usd": round(total / orders * 1000, 4) if orders else None,
        "assumptions": [
            f"Rates: {RATE_TABLE['region']} on-demand, effective {RATE_TABLE['effective_date']} (approximate).",
            f"App instances: average {usage['avg_instances']:.2f} in service ({usage['source']}).",
            "One Locust t3.small, one db.t3.micro and one ALB (2 nodes) are assumed running for the whole period.",
            f"ALB LCUs estimated as {a['lcu_base']} + requests/s / {a['rps_per_extra_lcu']}.",
            f"EBS {a['app_ebs_gb']} GB per instance, RDS storage {a['rds_storage_gb']} GB; CloudWatch is a flat rate.",
            "S3, ECR and data transfer are negligible and not included.",
        ],
    }
