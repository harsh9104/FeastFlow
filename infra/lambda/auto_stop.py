"""FeastFlow cost guard: park (or resume) the whole stack.

Invoked nightly by EventBridge with {"action": "stop"}. It can also be run by hand:
  aws lambda invoke --function-name feastflow-auto-stop --payload '{"action":"start"}' out.json
stop : ASG min/desired -> 0, Locust EC2 stopped, RDS stopped.
start: RDS started, Locust EC2 started, ASG min/desired -> ASG_MIN (instances fail
       health checks and get replaced until RDS is available, which is harmless).
Runs as LabRole (Learner Lab cannot create roles).
"""

import os

import boto3

ASG_NAME = os.environ["ASG_NAME"]
DB_ID = os.environ["DB_ID"]
PROJECT = os.environ.get("PROJECT", "FeastFlow")
ASG_MIN = int(os.environ.get("ASG_MIN", "1"))

asg = boto3.client("autoscaling")
ec2 = boto3.client("ec2")
rds = boto3.client("rds")


def _locust_ids(states):
    res = ec2.describe_instances(
        Filters=[
            {"Name": "tag:Name", "Values": ["feastflow-locust"]},
            {"Name": "tag:Project", "Values": [PROJECT]},
            {"Name": "instance-state-name", "Values": states},
        ]
    )
    return [i["InstanceId"] for r in res["Reservations"] for i in r["Instances"]]


def _db_status():
    try:
        return rds.describe_db_instances(DBInstanceIdentifier=DB_ID)["DBInstances"][0][
            "DBInstanceStatus"
        ]
    except rds.exceptions.DBInstanceNotFoundFault:
        return "missing"


def stop():
    done = {}
    asg.update_auto_scaling_group(AutoScalingGroupName=ASG_NAME, MinSize=0, DesiredCapacity=0)
    done["asg"] = "scaled to 0"
    ids = _locust_ids(["pending", "running"])
    if ids:
        ec2.stop_instances(InstanceIds=ids)
    done["locust"] = ids or "already stopped"
    status = _db_status()
    if status == "available":
        rds.stop_db_instance(DBInstanceIdentifier=DB_ID)
        done["rds"] = "stopping"
    else:
        done["rds"] = f"left as {status}"
    return done


def start():
    done = {}
    status = _db_status()
    if status == "stopped":
        rds.start_db_instance(DBInstanceIdentifier=DB_ID)
        done["rds"] = "starting"
    else:
        done["rds"] = f"left as {status}"
    ids = _locust_ids(["stopped"])
    if ids:
        ec2.start_instances(InstanceIds=ids)
    done["locust"] = ids or "none stopped"
    asg.update_auto_scaling_group(
        AutoScalingGroupName=ASG_NAME, MinSize=ASG_MIN, DesiredCapacity=ASG_MIN
    )
    done["asg"] = f"min/desired {ASG_MIN}"
    return done


def handler(event, context):
    action = (event or {}).get("action", "stop")
    if action not in ("stop", "start"):
        raise ValueError(f"unknown action {action!r}")
    result = stop() if action == "stop" else start()
    print({"action": action, **result})
    return {"action": action, **result}
