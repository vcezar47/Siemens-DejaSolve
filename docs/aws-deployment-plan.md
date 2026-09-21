# AWS deployment plan — the real build

Revised 24 Aug: this replaces the App-Runner-only draft. Given four weeks of hands-on work with VPC, Aurora,
DynamoDB, S3, CloudFormation, EC2 and IAM, the plan below builds the actual "at scale" row from
[docs/architecture.md](architecture.md) rather than a single-container stand-in for it.

Templates live in [`infra/cloudformation/`](../infra/cloudformation/): `network.yaml`, `data.yaml`,
`ollama.yaml`, `compute.yaml`, deployed in that order via cross-stack exports (no nested stacks — plain
`Fn::ImportValue`, so each layer can be redeployed or torn down independently, which matters more here than
DRY-ness). `ollama.yaml` must come before `compute.yaml` — the `ui` task's `OLLAMA_URL` imports its export.

| Layer (docs/architecture.md) | Template | Resources |
|---|---|---|
| Networking | `network.yaml` | VPC, 2 public + 2 private subnets, 1 NAT gateway, security groups scoped ALB→ECS→Aurora→Ollama |
| 1 · Ingest | `data.yaml` (queue) + `compute.yaml` (worker) | SQS + DLQ, ECS Fargate `ingest-worker` service |
| 1 · Ingest, model backend | `ollama.yaml` | CPU-only EC2 instance running Ollama — see §2.5, GPU is quota-blocked on this account |
| 2 · Archive + retrieval | `data.yaml` | Aurora Serverless v2 (Postgres, `pgvector`), S3 bucket for raw artifacts |
| 3 · Verifier | — | Stays a stateless library inside whichever service calls it, exactly as `docs/architecture.md` already argues — no infrastructure to add |
| 4 · Solve | not built here | see §5 — lowest demo value per hour of the remaining rows, left out on purpose |
| audit trail | `data.yaml` | DynamoDB table, `case_id` / `recorded_at` keys — `trace["audit"]` is already append-only and case-keyed, which is a DynamoDB access pattern, not a relational one |
| Compute | `compute.yaml` | ECS Fargate cluster, `ui` service behind an ALB, `ingest-worker` service, per-service IAM task roles (not one shared role) |

One NAT gateway rather than one-per-AZ, and no WAF/ACM/custom domain — those buy production HA and TLS
posture this project doesn't need for a graded demo, at a running cost this account doesn't need to carry.

---

## 1. Before deploying

- Region: pick one and pass it consistently (`--region eu-central-1` or whichever you're already using for
  the other work). All three templates assume everything lives in one region.
- The zero-spend budget alert from the earlier draft is worth keeping regardless of how basic it sounds —
  this stack has an always-on cost floor (NAT + Aurora + ALB, see §4) that a paused App Runner service didn't,
  so an alert that fires on the first unexpected dollar is cheap insurance.
- `network.yaml` and `data.yaml` take no image — deploy those first, independent of the app build.

## 2. Deploy — via the console

A note on exactness, since it matters more here than in a CLI doc: the overall shape of the CloudFormation
console wizard — upload a template, fill in parameters, review, tick the IAM-capabilities box, create — has
been stable for years and is described with confidence below. Exact button wording can drift a little with
console redesigns; where something on your screen doesn't match a label here, trust your screen — the action
being described is the constant, not the exact pixel. The console's **search bar at the top of every page**
(type a service name, hit enter) is the one piece of navigation that's stayed put across every redesign, so
that's what these steps use to get to each service rather than describing a specific sidebar layout.

### 2.1 Stack 1 — networking

1. Search bar → **CloudFormation**.
2. **Create stack** → **With new resources (standard)**.
3. **Template source: Upload a template file** → choose `infra/cloudformation/network.yaml` from this repo
   → **Next**.
4. **Stack name**: this can be anything (`dejasolve-network` is fine) — it's just this stack's own label and
   is never referenced by the other two. What *is* shared across all three stacks is the **EnvironmentName**
   parameter, which defaults to `dejasolve`. Leave it at the default and leave it identical in stacks 2 and 3
   too — that string, not the stack name, is what the exports/imports between templates are keyed on. Leave
   the CIDR parameters at their defaults unless they'd collide with something else in your account → **Next**.
5. Leave stack options at their defaults → **Next**.
6. On the review page, this template only creates security groups and networking resources — no IAM, so
   there may be nothing to acknowledge here. If a capabilities checkbox is shown anyway, check it. **Submit**.
7. Wait for the stack's status to reach **CREATE_COMPLETE** — watch the **Events** tab if you want to see
   each resource come up, or just refresh the stack list.
8. Open the **Outputs** tab once it's done. You won't need to copy anything from it by hand — stacks 2 and 3
   pull these values automatically as long as their own **EnvironmentName** parameter matches this stack's
   (`dejasolve`) — but it's worth glancing at to confirm `VpcId` and the subnet IDs are populated.

### 2.2 Stack 2 — data layer (Aurora, S3, SQS, DynamoDB, bastion)

1. CloudFormation → **Create stack** → **With new resources (standard)**.
2. **Upload a template file** → `infra/cloudformation/data.yaml` → **Next**.
3. **Stack name**: anything, e.g. `dejasolve-data`. In the parameters list, **EnvironmentName must be set to
   the exact same value as stack 1** (`dejasolve`, if you left that at its default) — the template's
   `Fn::ImportValue` calls look for exports named `<EnvironmentName>-PrivateSubnet1Id` etc., so a mismatch
   here is a silent "no export found" failure at creation time, not a typo caught earlier. Leave the other
   parameters at their defaults unless you want a larger Aurora ceiling → **Next**.
4. **Next** through stack options.
5. Review page: this stack creates an IAM role for the bastion instance, so check the box acknowledging
   CloudFormation may create IAM resources (it should be near the bottom, above the submit button) →
   **Submit**.
6. Wait for **CREATE_COMPLETE** — Aurora is the slow part here, often several minutes, so don't worry if this
   one takes longer than stack 1 did.
7. **Outputs** tab: note `AuroraClusterEndpoint`, `AuroraSecretArn`, and `BastionInstanceId` (or just leave
   the tab open) — you'll need them for the pgvector step below.

**If `AuroraCluster` fails with "To use Aurora clusters with free plan accounts you need to set
WithExpressConfiguration... To remove all limitations, upgrade your account plan":** this is an
account-tier restriction on brand-new AWS accounts (the "Free Plan," distinct from the older Free Tier), not
a template problem — everything before it (VPC, S3, SQS, DynamoDB) succeeds because they aren't gated this
way. Fix, per AWS's own free-tier FAQ: Billing and Cost Management console → the **Cost and Usage** widget on
the account overview → **Upgrade Plan**. One caveat before confirming: if the account was created under an
AWS Organization, Control Tower, or the Partner Network, upgrading forfeits remaining Free Tier credits
immediately — shouldn't apply to a personal account, but worth checking the confirmation screen. Once
upgraded, delete the rolled-back `dejasolve-data` stack and recreate it unchanged.

### 2.3 Build and push the image — the one step that needs a terminal

There is no website-only way to build and push a Docker image; a browser can't do that, so this doc isn't
going to pretend otherwise. The ECR console does remove the guesswork of the exact commands, though:

1. Search bar → **ECR** → **Repositories** → **Create repository**.
2. Visibility: **Private**. Name: `dejasolve`. Leave the rest at defaults → **Create repository**.
3. Open the new repository → **View push commands** (a button near the top of the repository page). This
   generates the exact `docker login` / `build` / `tag` / `push` commands for *your* account and region —
   copy them from there rather than from this doc, since they embed your account ID and region.
4. Run those four commands in a terminal, from the `Siemens-DejaSolve` directory (the one containing the
   `Dockerfile`). It's the same image `docker compose up` already builds — nothing about it changes for AWS.
5. Back in the ECR console, refresh the repository page — the `latest` tag should now be listed with a
   pushed timestamp and a digest.
6. Copy the **image URI** shown next to that tag
   (`<account-id>.dkr.ecr.<region>.amazonaws.com/dejasolve:latest`) — stack 3 needs it as a parameter.

### 2.4 Stack 3 — compute (ALB, ECS cluster, services)

1. CloudFormation → **Create stack** → **Upload a template file** → `infra/cloudformation/compute.yaml` →
   **Next**.
2. **Stack name**: anything, e.g. `dejasolve-compute`. Parameters:
   - **EnvironmentName**: the same value again — `dejasolve` — so this stack's imports resolve against
     stacks 1 and 2
   - **ImageUri**: paste the URI copied in 2.3
   - **IngestWorkerDesiredCount**: leave at `0` — see the note on `dejasolve/cloud/ingest_worker.py` in §3, it doesn't exist
     yet, and this parameter defaulting to `0` is what keeps that service from crash-looping
   → **Next**.
3. **Next** through stack options.
4. Review page → this stack creates the task execution role and two task-specific IAM roles, so check the
   IAM-capabilities acknowledgement → **Submit**.
5. Wait for **CREATE_COMPLETE**. This one also takes a few minutes — the ECS service has to place a task and
   pass its first health check before CloudFormation calls the stack done.
6. **Outputs** tab → `AlbDnsName` is the demo URL. Open `http://<that value>/` in a browser — it should be
   the same page `docker compose up` shows locally.

**If the `ui` service never goes healthy**, the CloudFormation stack view won't tell you why on its own.
Search bar → **ECS** → **Clusters** → `dejasolve-cluster` → **Services** tab → `dejasolve-ui` → **Tasks** tab
→ click the running (or stopped) task → **Logs** tab shows the container's stdout, which is where a startup
error would appear.

### 2.5 Ollama on EC2 (CPU) — the model backend, in the VPC

GPU instance families came back with a **quota of 0** on this account (checked via Service Quotas before
writing this, not assumed) — a known default on new AWS accounts, and a support-ticket-and-wait situation
this close to a deadline isn't worth risking. `ollama.yaml` runs Ollama on an 8-vCPU CPU-only instance
instead, which is well inside the *Standard* family's quota (16 vCPUs, alongside the bastion's 2) and doesn't
need any request at all. The tradeoff, stated plainly rather than discovered live: CPU inference on a 7B
model is slower than even your laptop's partial-GPU setup — this task is short structured JSON extraction
rather than long-form generation, which is the case CPU handles least badly, but it hasn't been benchmarked
end-to-end, so budget time to actually test it before trusting it on stage.

1. CloudFormation → **Create stack** → **Upload a template file** → `infra/cloudformation/ollama.yaml` →
   **Next**.
2. **Stack name**: anything, e.g. `dejasolve-ollama`. **EnvironmentName**: `dejasolve`, matching every other
   stack. Leave `InstanceType` (`c5.2xlarge`) and `OllamaModel` (`qwen2.5:7b`) at their defaults → **Next**.
3. **Next** through stack options.
4. Review page → check the IAM-capabilities acknowledgement (this creates the instance's SSM role) →
   **Submit**.
5. Wait for **CREATE_COMPLETE** — this only confirms the *instance* exists, not that Ollama has finished
   installing and pulling a 4.7 GB model inside it. Give it several more minutes after the stack finishes.
6. Verify it's actually ready before moving on: Search bar → **EC2** → **Instances** → the instance tagged
   `dejasolve-ollama` → **Connect** → **Session Manager** tab → **Connect**, then in that terminal:
   ```bash
   curl http://127.0.0.1:11434/api/tags
   ```
   Should list `qwen2.5:7b`. If it doesn't yet, check `cat /var/log/cloud-init-output.log` in that same
   session for where the install/pull script is stuck — that log has the full output of everything the
   instance's startup script ran.
7. **Update `dejasolve-compute`**: CloudFormation → `dejasolve-compute` → **Update** → **Replace current
   template** → upload the updated `compute.yaml` (now requests `OllamaUrl` from this stack) → keep the
   existing parameter values → proceed to **Update stack**.
8. Confirm: open `/api/health` on the `AlbDnsName` URL. `backends.ollama.available` should now be `true`,
   and `backends.hybrid.available` should follow it — that's what makes `hybrid` selectable in the page's
   dropdown again, same as it is locally.

**Cost note, since this is the priciest single thing in the stack now:** `c5.2xlarge` is roughly $0.34/hr in
`eu-west-2` — call it $8/day if left running continuously. **Stop, don't terminate**, the instance between
sessions (EC2 console → select it → **Instance state** → **Stop**): stopping halts compute billing while
keeping the 30 GB EBS volume (and the already-pulled model on it) intact, so you're not re-downloading 4.7 GB
every morning. Terminating loses that volume and starts the pull over on the next `CREATE_COMPLETE`.

---

## pgvector + schema — one-time, via Session Manager in the console

1. Search bar → **EC2** → **Instances** → find the instance tagged `dejasolve-bastion`.
2. Select it → **Connect** (button near the top of the instance details) → **Session Manager** tab →
   **Connect**. This opens a browser-based terminal directly to the instance — no SSH key and no open
   inbound port needed, because the bastion's security group in `network.yaml` has no inbound rules at all;
   Session Manager reaches it over a connection the instance itself initiates outbound.
3. In a second browser tab, search bar → **Secrets Manager** → find the secret attached to the Aurora
   cluster (its ARN is the `AuroraSecretArn` output from stack 2) → open it → **Retrieve secret value** →
   copy the `password` field.
4. Back in the Session Manager terminal tab, connect with `psql` (install it first if the Amazon Linux base
   image doesn't already have it — `sudo dnf install -y postgresql15` covers that):
   ```
   psql -h <AuroraClusterEndpoint from stack 2 Outputs> -U dejasolve_admin -d dejasolve
   ```
   paste the password when prompted, then run:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

That's the one step this template can't do for you — creating a Postgres extension is a SQL statement, not a
CloudFormation resource type, so it has to happen after the cluster already exists. Whatever `cases` table
shape retrieval will actually query against is created the same way, and is part of the wiring work in §3
rather than this bootstrap step.

## 3. Wired in — the three follow-ups, now built

All three pieces of code named in the original draft of this section exist now, each additive rather than a
replacement, so `run_all.py` / `benchmarks/bench.py` / every benchmarked number on the deck still goes through the
original file-backed `dejasolve.Archive` untouched:

1. **`dejasolve/cloud/ingest_worker.py`** — long-polls `IngestQueue`, pulls an artifact from S3, calls the existing
   `ingest.ingest_text()` unchanged, writes the resulting Case Card to `s3://<bucket>/cards/<name>.json`.
2. **`dejasolve/cloud/archive_aurora.py`** — `AuroraArchive`, a subclass of `dejasolve.Archive` that overrides `__init__`
   (loads from the `cases` table instead of a file) and `nearest()` (a real pgvector `<->` query instead of
   `numpy.linalg.norm`) — both normalise against the same fixed `PARAM_BOUNDS`, so it returns the *same*
   nearest case for the same query, not an approximation. `nearest_failure()`/`nearest_on()` are inherited
   unchanged. `app.py`'s `archive()` factory picks this over the file-backed one when `RETRIEVAL_BACKEND=aurora`
   — otherwise nothing changes. `dejasolve/cloud/sync_archive_to_aurora.py` populates the table (creates it on first run,
   upserts on every run after).
3. **DynamoDB audit mirror** — `app.py`'s `/api/analyse` now calls `_mirror_audit_to_dynamo(trace)` after
   every request, a best-effort write of `trace["audit"]` into the `AUDIT_TABLE` (no-op if that env var isn't
   set; never allowed to fail the response it's attached to).

**One robustness fix that came out of building this:** `/api/health` used to call `archive()` unconditionally
— fine when that only ever read a local file, but once it can reach out to Aurora, a hiccup there would have
failed the health check itself and gotten the ECS task killed and cycled by the ALB. `/api/health` now catches
that and reports `retrieval_backend` / `archive_error` as fields instead of raising, the same way it already
treats an unreachable Ollama as a reported state rather than a crash.

### Deploying the update

1. Rebuild and push the image — same steps as §2.3 (`docker build`, `docker tag`, `docker push`); it now
   includes `boto3`/`psycopg2-binary` and the three new files.
2. **Populate Aurora**, once: Search bar → **ECS** → **Clusters** → `dejasolve-cluster` → **Tasks** tab →
   **Run new task**. Launch type **FARGATE**, task definition `dejasolve-ui` (any revision), same subnets and
   security group the `ui` service already uses (private subnets, `EcsSecurityGroup` — it needs to reach
   Aurora on 5432, which that security group already permits). Under **Container overrides**, change the
   `ui` container's command to `python -m dejasolve.cloud.sync_archive_to_aurora` → **Run task**. Check its logs (Task →
   **Logs** tab) for `synced N solved, M failed cases to Aurora`.
3. **Update the compute stack**: CloudFormation → `dejasolve-compute` → **Update** → **Replace current
   template** → upload the updated `compute.yaml` → **Next**. Set **ImageUri** to the freshly pushed tag,
   **RetrievalBackend** to `aurora`, and **IngestWorkerDesiredCount** to `1` (now that `dejasolve/cloud/ingest_worker.py`
   exists) → proceed through to **Update stack**.
4. Confirm: open `/api/health` on the `AlbDnsName` URL — `retrieval_backend` should read `"aurora"` and
   `archive_size` should match the synced count. Run an artifact through the UI as before; the retrieval stage
   now executes as a pgvector query against Aurora rather than an in-process numpy scan.

Nothing here is required to keep working for the deck — `RetrievalBackend` back to `file` (or just not
updating the stack) leaves the original, benchmarked path exactly as it was.

## 4. Cost — this stack has an always-on floor the App Runner draft didn't

| Resource | Rate | Monthly if left running |
|---|---|---|
| NAT Gateway | ~$0.045/hr + data processing | ~$33 |
| ALB | ~$0.0225/hr + LCU-hours | ~$16 + usage |
| Aurora Serverless v2 | ~$0.12/ACU-hr, floor 0.5 ACU | ~$43 minimum, even idle |
| Fargate (`ui`, 0.5 vCPU/1 GB) | ~$0.02/hr | ~$15 |
| Bastion `t3.micro` | free-tier eligible (750 hrs/mo, year one) | ~$0 |

That's roughly **$100+/month if simply left up**, against a credit meant to last the year. For a few days
around the 28th this is a few dollars, but the fix is the same one CloudFormation makes easy: **tear stacks
down between work sessions** rather than leaving them running, and only bring `compute` + `data` back up
ahead of a session that needs them (`network` can stay, it's cheap once NAT is the only thing in it — or tear
that down too and redeploy in under ten minutes when needed).

## 5. Deliberately not built

Same reasoning as the original architecture doc, now restated against this deployment rather than a diagram:

- **No pgvector/OpenSearch retrieval code, no ECS Batch solve jobs.** These are the two remaining
  "at scale" rows and the ones requiring the most new application code (a different retrieval backend, a
  job-per-case runner) for the least marginal demo value — the diagram already carries that argument
  credibly, and building them now risks the working, benchmarked local pipeline for a payoff the room won't
  weight highly against the measured numbers.
- **No multi-AZ Aurora, no WAF, no custom domain/ACM cert.** Production hardening a ten-minute student demo
  doesn't need and that costs money to carry.

## 6. Teardown — via the console

Reverse order, since `dejasolve-data` and `dejasolve-compute` import values from `dejasolve-network` —
CloudFormation refuses to delete a stack whose exports are still referenced elsewhere, so this order isn't
optional.

1. Search bar → **CloudFormation** → select the `dejasolve-compute` stack (click its name or its row
   checkbox) → **Delete** → confirm in the dialog that appears.
2. Wait for it to finish — either watch the **Events** tab or wait for it to drop off the stack list.
3. Select `dejasolve-data` → **Delete** → confirm. Wait for completion.
4. Select `dejasolve-network` → **Delete** → confirm.
5. Search bar → **ECR** → **Repositories** → select `dejasolve` → **Delete** → the console will ask you to
   type the repository name to confirm, since this destroys the pushed image itself, not just the stack that
   referenced it.

`DeletionProtection: false` on the Aurora cluster and no `Retain` deletion policies anywhere in these
templates, on purpose — nothing here is meant to outlive the project by accident, and none of the deletes
above should get stuck waiting on a protection flag.

## 7. One line for the deck, if you use any of this

> "The architecture slide isn't hypothetical — it's deployed: VPC, Aurora with pgvector, SQS, DynamoDB and
> the same container, running on ECS Fargate right now," then move to the measured numbers. The infra proves
> the platform claim; the iteration counts are still what the room should remember.
