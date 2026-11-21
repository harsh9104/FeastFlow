"""Admin Cloud & Cost panel, against moto's fake AWS."""

import pytest
from botocore.exceptions import ClientError

from app.core import aws
from app.core.config import get_settings
from app.services import cloud_service
from tests.conftest import auth, register
from tests.test_festival import admin

ASG = "feastflow-asg"


@pytest.fixture(autouse=True)
def fresh_cache():
    cloud_service.clear_cache()
    yield
    cloud_service.clear_cache()


@pytest.fixture
def stack(monkeypatch):
    """A small FeastFlow-like stack: ASG with 2 instances, ALB, RDS, Locust, alarms, budget."""
    ec2 = aws.service("ec2")
    subnets = [s["SubnetId"] for s in ec2.describe_subnets()["Subnets"]][:2]
    ami = ec2.describe_images()["Images"][0]["ImageId"]
    ec2.create_launch_template(
        LaunchTemplateName="feastflow-lt",
        LaunchTemplateData={"ImageId": ami, "InstanceType": "t3.micro"},
    )
    autoscaling = aws.service("autoscaling")
    autoscaling.create_auto_scaling_group(
        AutoScalingGroupName=ASG,
        LaunchTemplate={"LaunchTemplateName": "feastflow-lt"},
        MinSize=1,
        MaxSize=4,
        DesiredCapacity=2,
        VPCZoneIdentifier=",".join(subnets),
    )
    autoscaling.put_scaling_policy(
        AutoScalingGroupName=ASG,
        PolicyName="feastflow-cpu-60",
        PolicyType="TargetTrackingScaling",
        TargetTrackingConfiguration={
            "TargetValue": 60.0,
            "PredefinedMetricSpecification": {"PredefinedMetricType": "ASGAverageCPUUtilization"},
        },
    )
    aws.service("elbv2").create_load_balancer(Name="feastflow-alb", Subnets=subnets)
    aws.service("rds").create_db_instance(
        DBInstanceIdentifier="feastflow-db",
        DBInstanceClass="db.t3.micro",
        Engine="mysql",
        AllocatedStorage=20,
        MasterUsername="feastflow",
        MasterUserPassword="secret123",
    )
    locust = ec2.run_instances(ImageId=ami, InstanceType="t3.small", MinCount=1, MaxCount=1)
    locust_id = locust["Instances"][0]["InstanceId"]
    cw = aws.service("cloudwatch")
    for name, threshold in (("feastflow-high-cpu", 80), ("feastflow-orders-backlog", 200)):
        cw.put_metric_alarm(
            AlarmName=name,
            MetricName="CPUUtilization",
            Namespace="AWS/EC2",
            Statistic="Average",
            Period=60,
            EvaluationPeriods=1,
            Threshold=threshold,
            ComparisonOperator="GreaterThanThreshold",
        )
    cw.put_metric_alarm(  # someone else's alarm: must not show
        AlarmName="other-app-cpu",
        MetricName="CPUUtilization",
        Namespace="AWS/EC2",
        Statistic="Average",
        Period=60,
        EvaluationPeriods=1,
        Threshold=50,
        ComparisonOperator="GreaterThanThreshold",
    )
    cw.set_alarm_state(AlarmName="feastflow-orders-backlog", StateValue="ALARM", StateReason="test")
    account = aws.service("sts").get_caller_identity()["Account"]
    aws.service("budgets").create_budget(
        AccountId=account,
        Budget={
            "BudgetName": "feastflow-monthly",
            "BudgetType": "COST",
            "TimeUnit": "MONTHLY",
            "BudgetLimit": {"Amount": "50", "Unit": "USD"},
        },
    )
    for key, value in {
        "ASG_NAME": ASG,
        "ALB_NAME": "feastflow-alb",
        "RDS_INSTANCE_ID": "feastflow-db",
        "LOCUST_INSTANCE_ID": locust_id,
        "BUDGET_NAME": "feastflow-monthly",
    }.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_cloud_panel_is_admin_only(client):
    customer = register(client)["access_token"]
    assert client.get("/api/admin/cloud").status_code == 401
    assert client.get("/api/admin/cloud", headers=auth(customer)).status_code == 403


def test_not_configured_locally(client, db):
    res = client.get("/api/admin/cloud", headers=admin(client, db))
    assert res.status_code == 200
    assert res.json()["configured"] is False


def test_overview_reads_the_stack(client, db, stack):
    data = client.get("/api/admin/cloud", headers=admin(client, db)).json()
    assert data["configured"] is True

    asg = data["asg"]
    assert (asg["min"], asg["max"], asg["desired"], asg["cpu_target"]) == (1, 4, 2, 60.0)
    assert len(asg["instances"]) == 2
    assert all(i["launched_at"] for i in asg["instances"])

    names = [a["name"] for a in data["alarms"]["items"]]
    assert "other-app-cpu" not in names
    assert names[0] == "feastflow-orders-backlog"  # firing alarms first
    assert "feastflow-high-cpu" in names

    assert isinstance(data["activities"]["items"], list)  # moto keeps no activity history
    assert set(data["metrics"]) == {"cpu", "instances"}
    assert data["budget"]["limit"] == 50

    cost = data["cost"]
    by_item = {line["item"]: line for line in cost["lines"]}
    assert by_item["App servers (t3.micro)"]["qty"] == 2
    assert by_item["Locust load generator (t3.small)"]["qty"] == 1
    assert by_item["RDS MySQL (db.t3.micro)"]["qty"] == 1
    assert cost["unknown"] == []
    expected = 2 * 0.0104 + 0.0225 + 0.017 + 20 * 0.115 / 730 + 0.0208
    assert cost["per_hour"] >= round(expected, 4)  # plus public IPv4 addresses
    assert cost["per_day"] == round(cost["per_hour"] * 24, 2)


def test_stopped_database_only_costs_storage(client, db, stack):
    aws.service("rds").stop_db_instance(DBInstanceIdentifier="feastflow-db")
    cost = client.get("/api/admin/cloud", headers=admin(client, db)).json()["cost"]
    by_item = {line["item"]: line for line in cost["lines"]}
    assert by_item["RDS MySQL (db.t3.micro)"]["per_hour"] == 0
    assert by_item["RDS storage (20 GB)"]["per_hour"] > 0


def test_one_denied_call_does_not_break_the_panel(client, db, stack, monkeypatch):
    def denied(*args, **kwargs):
        raise ClientError({"Error": {"Code": "AccessDenied", "Message": "no"}}, "DescribeAlarms")

    monkeypatch.setattr(cloud_service, "_alarms", denied)
    data = client.get("/api/admin/cloud", headers=admin(client, db)).json()
    assert data["alarms"]["error"].startswith("AccessDenied")
    assert len(data["asg"]["instances"]) == 2


def test_failed_section_is_reported_as_unknown_cost(client, db, stack, monkeypatch):
    def denied(*args, **kwargs):
        error = {"Error": {"Code": "AccessDenied", "Message": "no"}}
        raise ClientError(error, "DescribeDBInstances")

    monkeypatch.setattr(cloud_service, "_rds", denied)
    cost = client.get("/api/admin/cloud", headers=admin(client, db)).json()["cost"]
    assert cost["unknown"] == ["database"]


def test_results_are_cached(client, db, stack, monkeypatch):
    headers = admin(client, db)
    client.get("/api/admin/cloud", headers=headers)
    calls = []
    monkeypatch.setattr(cloud_service, "_build", lambda: calls.append(1) or {})
    client.get("/api/admin/cloud", headers=headers)
    assert calls == []
