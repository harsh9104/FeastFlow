# 12 – AWS Learner Lab Constraints, Optional Services & Assumptions (CON-01)

> Learner Lab policies vary by course and change over time. Items marked **VERIFY** must be confirmed in *your* lab (for example, by trying the action in the console) before P5.

## 12.1 Known Learner Lab limitations and how the design handles them

| # | Limitation | Design response |
|---|---|---|
| L-01 | Regions limited to **us-east-1** / us-west-2 | Everything goes in us-east-1 |
| L-02 | **IAM: cannot create roles, users, policies or OIDC providers** | EC2 uses the pre-built `LabInstanceProfile` (`LabRole`). FR-12 is met via (a) LabRole for components, (b) **security groups** for network least privilege, (c) **S3 bucket policy** (resource policy, enforceable), and (d) a documented least-privilege policy `infra/policies/app-least-privilege.json` showing what would be attached in a real account. |
| L-03 | Session lasts about 4 h. EC2 instances are **stopped** at session end and restarted next session. | App is stateless and immutable (user-data boots the container), so the ASG can replace any instance. Expect ASG health replacements after a session resume. |
| L-04 | Session credentials expire | GitHub Actions secrets must be refreshed each session before a CD demo (AC-03). |
| L-05 | EC2 type & count caps (typically nano–large, about 9 concurrent instances, 32 vCPU) — **VERIFY** | ASG max 4 + Locust 1 + optional DB fallback 1 = **6 instances max** |
| L-06 | Credit budget (typically $50–$100) | Estimated about **$0.13/h** baseline (see 12.4). Guardrails in 12.5. |
| L-07 | Cost Explorer / Budgets usually unavailable — **VERIFY** | In-app cost estimate from a rate table × CloudWatch usage. The lab's own "used credits" figure is used as a cross-check in the final report. |
| L-08 | No domain → no ACM certificate | HTTP-only ALB **[ASSUMPTION A-08]**. Documented as a known limitation in the SLA/security notes. |
| L-09 | RDS: smaller classes only, Multi-AZ may be restricted — **VERIFY** | db.t3.micro single-AZ. Fallback is a Postgres container on a dedicated EC2. |
| L-10 | CodePipeline GitHub connection (CodeStar Connections) often blocked — **VERIFY** | GitHub Actions primary. CodeBuild/CodePipeline optional. |
| L-11 | ECR availability — **VERIFY** | Recommended. Fallback is a public image on GHCR. |
| L-12 | SSM Parameter Store / Session Manager availability — **VERIFY** | Optional. Fallback is env vars in launch template user-data, and EC2 Instance Connect for shell access. |

## 12.2 Service classification

| Service | Status | Justification |
|---|---|---|
| EC2 + Docker | **Required** | SRS compute |
| Application Load Balancer | **Required** | FR-08 |
| EC2 Auto Scaling Group | **Required** | FR-09 |
| CloudWatch (metrics, logs, alarms, agent) | **Required** | FR-10, FR-11 |
| IAM (LabRole / LabInstanceProfile) | **Required** (pre-provisioned) | FR-12 |
| S3 | **Required** | FR-13 |
| RDS PostgreSQL | **Required if permitted**, else EC2-hosted Postgres | FR-06, SRS |
| GitHub Actions | **Required** (chosen CI/CD) | FR-14 |
| Amazon ECR | **Recommended** | Image registry for CD |
| SNS | **[OPTIONAL]** | SRS: "optional SNS" |
| SSM Parameter Store | **[OPTIONAL]** | Secret hygiene |
| CodePipeline / CodeBuild | **[OPTIONAL]** alternative | SRS: "if permitted" |
| CloudFormation | **[OPTIONAL]** | IaC alternative to CLI scripts |
| RDS Multi-AZ | **[OPTIONAL]** | Higher availability at about 2× DB cost |

## 12.3 IAM design (FR-12) – intended least-privilege policy for app instances

This can't be attached in Learner Lab. It's a design artifact that documents intent, and LabRole is a superset of it.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Sid": "S3Assets", "Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::feastflow-<acct>-assets/*" },
    { "Sid": "ReadMetrics", "Effect": "Allow",
      "Action": ["cloudwatch:GetMetricData", "cloudwatch:DescribeAlarms",
                 "autoscaling:DescribeAutoScalingGroups", "autoscaling:DescribeScalingActivities",
                 "elasticloadbalancing:DescribeTargetHealth"], "Resource": "*" },
    { "Sid": "AgentAndLogs", "Effect": "Allow",
      "Action": ["cloudwatch:PutMetricData", "logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"],
      "Resource": "*" },
    { "Sid": "PullImage", "Effect": "Allow",
      "Action": ["ecr:GetAuthorizationToken", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"], "Resource": "*" },
    { "Sid": "Secrets", "Effect": "Allow", "Action": ["ssm:GetParameter"],
      "Resource": "arn:aws:ssm:us-east-1:<acct>:parameter/feastflow/*" }
  ]
}
```

Enforceable in the lab: an **S3 bucket policy** that denies non-TLS requests (`aws:SecureTransport = false`), with Block Public Access ON. Security groups are listed in [02](02-high-level-aws-architecture.md#security-groups-network-level-least-privilege).

**Separation of concerns (CON-02):** IAM decides *which AWS APIs the app may call*. The app's `users.role` and `users.subscription_tier` decide *what a person may do* and *how their orders are prioritised*. No IAM entity exists per end user.

## 12.4 Estimated hourly cost (us-east-1 on-demand, approximate – verify against current AWS pricing)

| Resource | Qty (baseline) | Rate | $/h baseline | $/h festival peak (4 app instances) |
|---|---|---|---|---|
| EC2 t3.micro (app) | 2 | $0.0104 | 0.0208 | 0.0416 |
| EC2 t3.small (Locust) | 1 | $0.0208 | 0.0208 | 0.0208 |
| ALB hours | 1 | $0.0225 | 0.0225 | 0.0225 |
| ALB LCU | about 1 / about 3 | $0.008 | 0.0080 | 0.0240 |
| RDS db.t3.micro PostgreSQL | 1 | ~$0.018 | 0.0180 | 0.0180 |
| RDS storage 20 GB gp3 | — | ~$0.115/GB-mo | 0.0032 | 0.0032 |
| EBS gp3 8 GB per EC2 | 3 / 5 | $0.08/GB-mo | 0.0026 | 0.0044 |
| Public IPv4 addresses | 5 / 7 (EC2 + ALB nodes) | $0.005 | 0.0250 | 0.0350 |
| CloudWatch (detailed monitoring, ~6 custom metrics, logs, alarms) | — | prorated | ~0.010 | ~0.015 |
| S3 + ECR storage | < 1 GB | — | < 0.001 | < 0.001 |
| **Total** | | | **≈ $0.13/h** | **≈ $0.19/h** |

Example: 40 lab hours of active use ≈ **$5–6**. That's well within typical Learner Lab credits.

## 12.5 Budget guardrails (NFR-03)

- ASG **max 4**. Launch template allows only `t3.micro`.
- Locust EC2 is stopped when no test is planned.
- CloudWatch log retention 7 days. ECR lifecycle keeps 10 images.
- No NAT Gateway, no Multi-AZ RDS, no Secrets Manager, no idle Elastic IPs.
- `99-teardown.sh` deletes everything tagged `Project=FeastFlow`.

## 12.6 Consolidated assumptions register

| ID | Assumption |
|---|---|
| A-01 | Premium is chosen at registration / toggled without payment. Admin can override. |
| A-02 | Menu is seeded. Admin menu CRUD is optional. |
| A-03 | Single seeded admin. Public sign-up creates customers only. |
| A-04 | Processing queue = PENDING orders by `priority DESC, created_at ASC`. |
| A-05 | Priority is snapshotted per order. |
| A-06 | Costs are estimates from public rates × measured usage. |
| A-07 | Memory metrics via CloudWatch agent. |
| A-08 | HTTP-only ALB (no domain/ACM in lab). |
| A-09 | Locust on a dedicated EC2 outside the ASG. |
| A-10 | Region us-east-1. |
| A-11 | Single restaurant, single currency. `total_amount` is informational. |
| A-12 | Load-test scenario sizes in doc 13 are starting values, calibrated after a baseline run. |
