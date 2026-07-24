# deploy-tracker

[![CI/CD](https://github.com/ri0mi/deploy-tracker/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/ri0mi/deploy-tracker/actions/workflows/ci-cd.yml)

A deployment tracking API that records releases and computes delivery metrics — deployed end to end by its own pipeline, onto infrastructure defined entirely in code.

This is a capstone project: the application, the container, the cloud infrastructure, and the delivery pipeline are all part of the same repository. A single `git push` runs the tests, builds and publishes the image, and rolls out the new version to a server that Terraform provisioned.

---

## Architecture

```
                    git push to main
                          │
                          ▼
        ┌─────────────────────────────────────┐
        │         GitHub Actions              │
        │                                     │
        │   test ──▶ build & push ──▶ deploy  │
        └──────────────┬──────────┬───────────┘
                       │          │
                       ▼          ▼
                 Docker Hub    SSH deploy
                       │          │
                       └────┬─────┘
                            ▼
        ┌─────────────────────────────────────┐
        │      AWS  (provisioned by Terraform)│
        │                                     │
        │   EC2 + Docker (via user_data)      │
        │   Security group  ·  Elastic IP     │
        │   Container + named volume          │
        └─────────────────────────────────────┘
```

Three layers, each defined in this repository:

| Layer | Technology | Location |
| ----- | ---------- | -------- |
| Application | FastAPI + SQLite | `app/` |
| Container | Docker | `Dockerfile` |
| Infrastructure | Terraform | `terraform/` |
| Delivery | GitHub Actions | `.github/workflows/` |

---

## What this project demonstrates

- Building a REST API with input validation, persistence, and a computed-metrics endpoint
- Containerizing a stateful application with a named volume so data survives redeploys
- Provisioning cloud infrastructure declaratively — instance, firewall rules, and a static IP
- Bootstrapping a server with `user_data` so it comes online with Docker already installed
- A three-stage pipeline where each stage gates the next
- Tagging images by commit SHA for traceability and rollback
- Managing credentials through encrypted secrets rather than committed files

---

## API

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| GET | `/health` | Health check |
| POST | `/deployments` | Record a deployment (service, version, status) |
| GET | `/deployments` | List deployments, optionally filtered by `?service=` |
| GET | `/metrics` | Total deployments, success/failure counts, success rate, per-service breakdown |

Interactive documentation is generated automatically at `/docs`.

Recording a deployment:

```bash
curl -X POST http://<host>:8000/deployments \
  -H "Content-Type: application/json" \
  -d '{"service":"deploy-tracker","version":"1.0.0","status":"success"}'
```

Reading the metrics:

```json
{
  "total_deployments": 4,
  "successful": 3,
  "failed": 1,
  "success_rate": 75.0,
  "services": [
    { "service": "deploy-tracker", "deployments": 3 },
    { "service": "static-site", "deployments": 1 }
  ]
}
```

The `status` field only accepts `success` or `failed` — anything else is rejected with a `422` before it reaches the database.

---

## The pipeline

Defined in [`.github/workflows/ci-cd.yml`](.github/workflows/ci-cd.yml). Every push to `main` triggers three jobs in sequence; each one runs only if the previous succeeded.

1. **test** — installs dependencies on a clean runner and runs the pytest suite.
2. **build-and-push** — builds the image and publishes it to Docker Hub under two tags: `latest` and the commit SHA.
3. **deploy** — connects to the EC2 instance over SSH, pulls the new image, and replaces the running container while keeping the data volume attached.

Pull requests run the test job only — images are published and deployed from `main` alone.

Tagging by commit SHA means every running container can be traced back to the exact commit that produced it, and any previous version can be redeployed by referencing its tag.

---

## The infrastructure

Defined in [`terraform/`](terraform/). Running `terraform apply` creates:

| Resource | Purpose |
| -------- | ------- |
| `aws_security_group` | Inbound SSH (22) and API (8000) access |
| `aws_instance` | `t3.micro` running Amazon Linux 2023 |
| `aws_eip` | Static IP so the deployment target doesn't change on restart |

Two details worth noting:

The AMI is resolved at plan time through a `data` source that queries AWS for the most recent Amazon Linux 2023 image, rather than pinning an AMI ID that would be region-specific and would age out.

The instance runs a `user_data` script on first boot that installs Docker, enables the service, and adds `ec2-user` to the docker group. The server is ready to receive a deployment without anyone connecting to it.

---

## Running locally

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

DB_PATH=./local.db uvicorn app.main:app --reload
```

The database path is read from the `DB_PATH` environment variable, defaulting to `/data/deployments.db` inside the container. Overriding it locally keeps development data out of the container's volume path.

Run the tests:

```bash
pytest -v
```

Tests use a temporary database and reset the table before each case, so they're independent of each other and of any local data.

---

## Running with Docker

```bash
docker build -t deploy-tracker .
docker run -d -p 8000:8000 -v deploy-data:/data deploy-tracker
```

The named volume mounted at `/data` is what makes the recorded deployments survive container replacement — the same mechanism the pipeline relies on when it rolls out a new version.

---

## Deploying the infrastructure

Requires the AWS CLI configured and an existing EC2 key pair.

```bash
cd terraform
terraform init
terraform plan  -var="key_name=<your-key-pair>"
terraform apply -var="key_name=<your-key-pair>"
```

Terraform outputs the instance ID, the elastic IP, and the API URL.

To tear everything down:

```bash
terraform destroy -var="key_name=<your-key-pair>"
```

### Required secrets

The pipeline expects these repository secrets:

| Secret | Purpose |
| ------ | ------- |
| `DOCKERHUB_USERNAME` | Docker Hub account |
| `DOCKERHUB_TOKEN` | Docker Hub access token |
| `EC2_HOST` | Elastic IP of the target instance |
| `EC2_USER` | SSH user (`ec2-user`) |
| `EC2_SSH_KEY` | Private key for the EC2 key pair |

---

## Notes and possible improvements

Deliberate simplifications, and what would change for a production setup:

- **Terraform state is local.** It should live in a remote backend (S3 with DynamoDB locking) so it can be shared and locked across a team.
- **Terraform runs manually.** A natural next step is running `plan` on pull requests and `apply` on merge, which requires the remote backend above plus AWS credentials scoped to the pipeline.
- **SSH is open to `0.0.0.0/0`** so the GitHub-hosted runner can reach the instance. AWS SSM Session Manager would remove the need to expose SSH at all.
- **SQLite on a single instance** suits one node. A managed database would be the move once the service needs more than one.
- **No HTTPS.** A load balancer with an ACM certificate, or a reverse proxy with Let's Encrypt, would terminate TLS.
- **No rollback automation.** Images are tagged by SHA, so rolling back is possible manually; wiring it into the pipeline would make it a one-click operation.
