---
title: GCP Service Account Impersonation Workaround for Key-Creation-Blocked Projects
date: 2026-04-13
author: Nate + Claude
memory_target: Mem0
scope: How to authenticate Python scripts to Google Cloud APIs (GA4 Data API, etc.) when the `iam.disableServiceAccountKeyCreation` org policy blocks the standard service-account-JSON-key flow.
confidence: high
supersedes: none
sources:
  - live_investigation: SmartScribe GCP project `ads-engin`, GA4 property `419769857`, on 2026-04-13
  - google_docs: https://cloud.google.com/iam/docs/service-account-creds
  - google_docs: https://cloud.google.com/iam/docs/impersonating-service-accounts
  - google_warning: gcloud CLI scope-deprecation warning emitted at auth time
---

# GCP Service Account Impersonation Workaround for Key-Creation-Blocked Projects

**Date:** 2026-04-13
**Memory target:** Mem0
**Scope:** GCP authentication for local Python scripts (ads_engine, jotbill_crm, any future harness that reads from a Google Cloud API) in projects where the default org policy blocks service account key creation.
**Status:** Canonical as of 2026-04-13. Validated end-to-end against GA4 Data API on SmartScribe's `ads-engin` project.

---

## TL;DR

New GCP projects ship with the `iam.disableServiceAccountKeyCreation` org policy enforced, which prevents downloading service-account JSON keys — the standard authentication pattern most tutorials and client libraries assume. The fallback pattern most people try next, `gcloud auth application-default login --scopes=...` with a sensitive scope like `analytics.readonly`, is also blocked by Google's default gcloud OAuth client as of early 2026. The correct workaround is **service account impersonation via Application Default Credentials**: the developer authenticates once as their user with default scopes, the service account holds the resource-level permission (e.g. GA Viewer), and the Python client mints short-lived SA tokens at runtime via the IAM Credentials API. No key file ever touches disk, no sensitive OAuth scope is requested through gcloud's default client, and the org policy is respected. A subtle Python-library gotcha will mislead you into thinking the setup is wrong when it isn't — `google.auth.default()` must be called with an explicit `cloud-platform` scope or impersonation fails with a misleading "getAccessToken denied" error.

---

## What Jot Should Commit to Memory

1. **When a new GCP project hits you with "Service account key creation is disabled" on the Keys tab, do not try to fix the org policy.** Pivot immediately to service account impersonation. Fighting the org policy requires the `roles/orgpolicy.policyAdmin` role at the org level — slower, more escalation paths, more blast radius — and the workaround works equally well for local developer use cases.

2. **Do not try `gcloud auth application-default login --scopes=https://www.googleapis.com/auth/analytics.readonly` (or any sensitive non-cloud-platform scope).** Google now blocks these scopes for the default gcloud OAuth client as part of their ADC scope restriction rollout. The browser will get an "App blocked" error page. This path is dead as of 2026 unless you create and distribute your own OAuth client ID, which is not worth it for a local-dev script.

3. **The correct authentication pattern for local scripts is:**
   - Developer runs `gcloud auth application-default login` one time with no custom scopes. This requests only `cloud-platform` scope, which is permitted.
   - A service account is created in the GCP project with a meaningful name (e.g. `ads-engine-ga-reader`).
   - The service account is granted the resource-level permission it needs (e.g. Viewer on a specific GA4 property, Viewer on a specific BigQuery dataset).
   - The developer's user is granted `roles/iam.serviceAccountTokenCreator` **on the specific service account** (not project-wide).
   - The IAM Credentials API (`iamcredentials.googleapis.com`) is enabled on the GCP project.
   - The Python client uses `google.auth.impersonated_credentials.Credentials` to wrap the user ADC and mint short-lived tokens for the service account at call time.

4. **Project Owner role does NOT implicitly include `iam.serviceAccounts.getAccessToken`.** Despite being marketed as a "superset" role, Google has excluded impersonation permissions from Owner as a security hardening measure. You must explicitly grant Token Creator on the target service account, even if you're already a project Owner. This is the single most common tripwire in this workflow.

5. **The Python library gotcha that will waste 30 minutes if you don't know about it:** `google.auth.default()` returns scopeless credentials by default. When those are passed as the `source_credentials` to `impersonated_credentials.Credentials`, the impersonation call fails with `iam.serviceAccounts.getAccessToken` denied — even though the Token Creator role is correctly granted. The error message is misleading; the actual problem is that the source credential doesn't have the `cloud-platform` scope needed to call the IAM Credentials API. The fix is one line: pass `scopes=["https://www.googleapis.com/auth/cloud-platform"]` explicitly to `google.auth.default()`.

6. **Required prerequisites for the workaround to succeed, in order of "if this is missing you get a confusing error":**
   - The IAM Credentials API must be enabled on the project. Check at `https://console.cloud.google.com/apis/library/iamcredentials.googleapis.com?project=<PROJECT>`. Enabling is instant but propagation can take up to 60 seconds.
   - The service account must exist.
   - The developer must have `roles/iam.serviceAccountTokenCreator` on that specific service account. Grant via IAM & Admin → Service Accounts → click SA → Permissions tab → Grant Access.
   - The service account must have the resource-level permission it needs on the target (e.g. Viewer on a GA4 property). Grant via the target resource's admin UI, not via GCP IAM.
   - ADC must be authenticated (`gcloud auth application-default login`) with a quota project set (`gcloud auth application-default set-quota-project <PROJECT>`).

7. **This workaround is appropriate for local developer workflows on a human's laptop. It is NOT appropriate for unattended/scheduled workflows** (cron jobs, CI/CD, scheduled cloud functions) because it relies on the developer's personal ADC credentials, which are tied to a human user and can expire or be revoked. For scheduled workflows, the correct pattern is either (a) Workload Identity Federation, (b) a service account running on GCE/Cloud Run/Cloud Functions where the runtime provides the identity automatically, or (c) getting the org policy carved out and using a real service account key.

8. **Canonical reference for future JotPsych/SmartScribe scripts that need GA4 data:** property ID `419769857` is the `www.jotpsych.com` marketing property (measurement ID `G-B7Q5FRBQRH`, data stream routed through the Cloud Run server-side tagging container at `server-side-tagging-z4zkeg2xnq-uc.a.run.app`). The GCP project for ads_engine authentication is `ads-engin` (note: truncated project ID, no final "e"). The canonical service account is `ads-engine-ga-reader@ads-engin.iam.gserviceaccount.com`.

---

## Why (Reasoning + Evidence)

### The org policy block

Google began enforcing `iam.disableServiceAccountKeyCreation` by default on new projects in 2024 as part of their "Secure by Default" rollout[^1]. Service account JSON keys are considered a security risk because they are long-lived bearer tokens that can be extracted from compromised machines or checked into source control. Enterprise GCP tenants are strongly encouraged to keep this policy enforced at the organization level and use either Workload Identity Federation (for cross-cloud workloads) or impersonation-based flows (for local development) instead.

The practical consequence for SmartScribe: on 2026-04-13, Nate attempted to create a JSON key for the newly-created `ads-engine-ga-reader` service account via **IAM & Admin → Service Accounts → ads-engine-ga-reader → Keys → Add Key → Create new key → JSON** and was met with a blocking dialog titled "Service account key creation is disabled"[^2]:

> An Organization Policy that blocks service accounts keys creation has been enforced on your organization.
>
> Enforced Organization Policies: `iam.disableServiceAccountKeyCreation`

The dialog offered two paths: (a) contact the Organization Policy Administrator to disable the constraint, or (b) "choose a more secure alternative" (i.e., impersonation or Workload Identity Federation).

### Why the `gcloud auth application-default login --scopes=analytics.readonly` fallback doesn't work either

The natural second attempt — having the developer authenticate with user credentials and request the sensitive scope directly — is also blocked. Running `gcloud auth application-default login --scopes=https://www.googleapis.com/auth/analytics.readonly,https://www.googleapis.com/auth/cloud-platform` emits this warning at the terminal before opening the browser[^3]:

> WARNING: The following scopes will be blocked soon for the default client ID: `https://www.googleapis.com/auth/analytics.readonly`. To use these scopes, you must provide your own client ID or use service account impersonation. Please refer to the documentation for more information.

And then, when the browser opens, Google's OAuth consent screen shows:

> This app is blocked. This app tried to access sensitive info in your Google Account. To keep your account safe, Google blocked this access.

The default client ID that gcloud ships with (`764086051850-6qr4p6gpi6hn506pt8ejuq83di341hur.apps.googleusercontent.com`) is no longer authorized by Google to request sensitive scopes like `analytics.readonly`. The only way to make user ADC work with those scopes would be to register your own OAuth client ID in a GCP project, configure a consent screen, and distribute it — which is non-trivial and inappropriate for a local-dev use case.

Google's official recommendation, printed verbatim in the warning: **"use service account impersonation."**

### How impersonation works

Service account impersonation lets a user with appropriate IAM permissions mint short-lived access tokens on behalf of a service account. The flow looks like this:

1. The developer authenticates once with `gcloud auth application-default login` (no custom scopes — only `cloud-platform`, which is always allowed).
2. The developer's user is granted `roles/iam.serviceAccountTokenCreator` on the target service account. This role contains a single permission: `iam.serviceAccounts.getAccessToken`.
3. At runtime, the Python code constructs an `impersonated_credentials.Credentials` object that wraps the user ADC. When a Google API call is made, the Python client library automatically:
   a. Uses the user ADC to authenticate a call to `iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/<SA_EMAIL>:generateAccessToken`.
   b. Requests a short-lived (≤1 hour) access token for the service account with the target scopes (e.g. `analytics.readonly`).
   c. Uses that token to authenticate the actual API call.
4. The target API (GA4 Data API in this case) sees the request as coming from the service account, not from the user. Resource-level permissions are enforced on the service account identity.

The security benefits vs. a downloaded JSON key: no long-lived credential is ever at rest anywhere. Tokens live for minutes, not years. If the developer's laptop is compromised, the attacker can only operate as the service account for as long as they can sustain the user-level ADC token, and only within the scope of whatever service accounts that user has Token Creator on — which is bounded and auditable.

### The Python library gotcha

On 2026-04-13 at ~17:05 PT, the first attempt to run the smoke test against GA4 property `419769857` with the impersonation path correctly set up in Python failed with this error:

```
grpc._channel._InactiveRpcError: <_InactiveRpcError of RPC that terminated with:
  status = StatusCode.UNAVAILABLE
  details = "Getting metadata from plugin failed with error: ('Unable to acquire impersonated credentials', '{
    \"error\": {
      \"code\": 403,
      \"message\": \"Permission 'iam.serviceAccounts.getAccessToken' denied on resource (or it may not exist).\",
      \"status\": \"PERMISSION_DENIED\"
    }
  }')"
```

The error suggested either that the service account didn't exist or that the caller lacked Token Creator on it. Both were verified to be false: the service account existed (confirmed via direct `GET` on `iam.googleapis.com/v1/projects/ads-engin/serviceAccounts/ads-engine-ga-reader@...`), the Token Creator grant was in place (confirmed via `getIamPolicy` on the service account, which returned a binding with `roles/iam.serviceAccountTokenCreator` for `user:nate@smartscribe.health`), and the IAM Credentials API was enabled (confirmed via `serviceusage.googleapis.com` showing `state: ENABLED`).

The raw-level curl test bypassed Python entirely and worked perfectly — using ADC to call `iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/<SA>:generateAccessToken` returned a valid `accessToken` with the requested `analytics.readonly` scope, and that token successfully called the GA4 Data API and returned real data rows. End-to-end at the HTTP level: fine. End-to-end through Python's `google.auth` library: broken.

The root cause, found by reading the source of `google.auth.impersonated_credentials.Credentials`: the class requires the `source_credentials` to have sufficient scope to call the IAM Credentials API (`cloud-platform` or `iam` scope). `google.auth.default()` returns user credentials with **no scopes** by default — the scopes are read from the ADC file only if explicitly requested. When impersonated_credentials wraps a scopeless source, the runtime attempts to refresh the source token before making the IAM API call, that refresh mints a token with no scopes, and the IAM Credentials API rejects it with `PERMISSION_DENIED` on `iam.serviceAccounts.getAccessToken` — which is the Token Creator permission, hence the misleading error message.

The one-line fix, documented in the source of `engine/tracking/ga_tracker.py` for future readers:

```python
# Source creds need cloud-platform scope to call IAM Credentials API
# for impersonation. google.auth.default() returns scopeless creds
# by default, which produces a misleading "getAccessToken denied" error.
source_creds, _ = google.auth.default(
    scopes=["https://www.googleapis.com/auth/cloud-platform"],
)
```

With that one change, the smoke test ran successfully and pulled 15 rows from GA4 property `419769857`, including the first post-CSP-fix marketing-site traffic.

---

## How to Apply

| Situation | Response |
|---|---|
| You need to authenticate a local Python script to a Google Cloud API (GA4 Data, BigQuery, Cloud Logging, etc.) and the GCP project is in an org with `iam.disableServiceAccountKeyCreation` enforced | Use the impersonation workaround. Do not try to create a JSON key. |
| You're following a tutorial that says "download the service account JSON key and set `GOOGLE_APPLICATION_CREDENTIALS`" | Adapt the tutorial. The SA concept is still correct; the key-file step is blocked. Use impersonation instead. |
| You hit `iam.serviceAccounts.getAccessToken denied` when running impersonation code | First check: is `google.auth.default()` called with `scopes=["https://www.googleapis.com/auth/cloud-platform"]`? That's the Python gotcha and resolves ~80% of these errors. Second check: is the IAM Credentials API enabled on the project? Third check: is Token Creator role granted to your user on the specific SA? |
| You're setting up a **scheduled / unattended** job (cron, CI, Cloud Functions) that needs Google Cloud auth | Do NOT use this workaround — it depends on a human user's ADC. Use a GCE/Cloud Run service identity, Workload Identity Federation, or negotiate an org policy carveout for a key-based SA. |
| You're an SDR or CS agent who doesn't touch infrastructure and someone asks you about GCP authentication | Escalate to Marcus or Nate. This brief is for the engineering team, not customer-facing work. |
| You're helping a SmartScribe engineer set up GA4 Data API access for the first time | Walk them through the `ads_engine` setup as the reference: project `ads-engin`, service account `ads-engine-ga-reader@ads-engin.iam.gserviceaccount.com`, GA property `419769857`, code in `engine/tracking/ga_tracker.py`. |

---

## What This Brief Does NOT Cover

- **Workload Identity Federation** — the correct pattern for cross-cloud workloads (e.g. a GitHub Actions workflow authenticating to GCP). That's a separate, more complex pattern and is overkill for the local-dev use case this brief addresses.
- **Creating your own OAuth client ID in GCP** to regain the ability to use user ADC with sensitive scopes. This is Google's other officially-supported path but involves setting up a consent screen and managing client secrets — not worth the overhead for local-dev scripts when impersonation is cleaner.
- **Negotiating an org-policy exception** with the GCP Organization Policy Administrator to actually disable `iam.disableServiceAccountKeyCreation` for a specific project. This is sometimes necessary for scheduled workloads, but it's a people-process decision and this brief doesn't opine on when to escalate vs. adapt.
- **Resource-level GA4 permission model** — what specifically Viewer vs. Analyst vs. Editor roles can do on a GA4 property. For our current use case (reading reports), Viewer is sufficient. If a future task needs to write custom definitions or manage measurements, a higher role is needed and this brief does not address that.
- **Scheduled / unattended workflows** — this brief is explicitly scoped to local developer workflows. Cron jobs, CI/CD pipelines, and scheduled cloud functions all need different authentication patterns.
- **Why the `iam.disableServiceAccountKeyCreation` org policy is a good idea in the abstract.** It is — bearer tokens at rest are genuinely a bad pattern. This brief just documents the workaround for cases where you don't have the authority or the desire to fight the policy.

---

## Open Questions

| Question | Owner | Resolution path |
|---|---|---|
| Should we migrate the GA4 pull to run on a schedule, and if so, how do we handle authentication when it can't rely on a human's ADC? | Nate + Marcus | Deferred until the manual pulls prove useful. Most likely path: either GCE/Cloud Run with a runtime identity, or negotiate an org-policy carveout for this one SA. |
| Is there a reason the project ID is `ads-engin` (truncated) rather than `ads-engine` (full)? | Nate | Probably just GCP's auto-generated project ID from the display name "ads-engine" clashing with an existing project somewhere in Google's namespace. Low priority. |
| Should other JotPsych/SmartScribe scripts that currently rely on service-account JSON keys (if any) be migrated to this pattern? | Marcus + Nate | Audit pending. If the current projects are in orgs that don't have the block enforced, they can keep working — but new projects will force this pattern. |

---

## Canonical Identifiers

| Thing | Value |
|---|---|
| GCP project ID (ads_engine auth) | `ads-engin` |
| GCP project number | `92024325903` |
| Service account email | `ads-engine-ga-reader@ads-engin.iam.gserviceaccount.com` |
| Service account unique ID | `105933137271740262200` |
| GA4 property ID (canonical www.jotpsych.com) | `419769857` |
| GA4 measurement ID (canonical) | `G-B7Q5FRBQRH` |
| GTM container ID (jotpsych.com + app.jotpsych.com) | `GTM-KL9RPN9V` |
| Server-side tagging endpoint | `https://server-side-tagging-z4zkeg2xnq-uc.a.run.app` |
| Required GCP API for impersonation | `iamcredentials.googleapis.com` |
| IAM role name for impersonation | `roles/iam.serviceAccountTokenCreator` |
| GA4 permission name (minimum for reads) | `Viewer` |
| Python library for GA4 Data API | `google-analytics-data` (>=0.18.0) |
| Python library for impersonation | `google.auth.impersonated_credentials` (bundled with `google-auth`) |
| ads_engine source file for GAClient | `engine/tracking/ga_tracker.py` |
| ads_engine CLI for landing-page pulls | `scripts/pull_ga_landing_pages.py` |
| ads_engine config for GA settings | `config/settings.py` (keys: `GA_PROPERTY_ID`, `GA_CREDENTIALS_PATH`, `GA_IMPERSONATE_SA`) |
| Scope required on source ADC creds | `https://www.googleapis.com/auth/cloud-platform` |
| Scope minted on impersonated SA token | `https://www.googleapis.com/auth/analytics.readonly` |
| Related CSP fix brief | `docs/jot-briefs/ga4-csp-fix-2026-04-13.md` (prerequisite — the GA pipe had to be alive before pulling data was useful) |

---

## Sources

[^1]: Google Cloud official guidance on service account key restrictions: https://cloud.google.com/iam/docs/best-practices-for-managing-service-account-keys and https://cloud.google.com/resource-manager/docs/organization-policy/restricting-service-accounts — both documents describe `iam.disableServiceAccountKeyCreation` as a recommended default for enterprise GCP tenants.

[^2]: Screenshot of the blocking dialog captured by Nate on 2026-04-13 during the Phase 3 (Download JSON key) step of setting up `ads-engine-ga-reader`. Dialog title: "Service account key creation is disabled". Text: "An Organization Policy that blocks service accounts keys creation has been enforced on your organization. Enforced Organization Policies: `iam.disableServiceAccountKeyCreation`."

[^3]: Terminal output captured during `gcloud auth application-default login --scopes=https://www.googleapis.com/auth/analytics.readonly,https://www.googleapis.com/auth/cloud-platform` on 2026-04-13. The warning references: https://docs.cloud.google.com/docs/authentication/troubleshoot-adc#access_blocked_when_using_scopes

[^4]: End-to-end verification log from `python3 scripts/pull_ga_landing_pages.py --days 7` on 2026-04-13 after the Python scope fix was applied. Returned 15 rows from GA4 property `419769857` including post-CSP-fix marketing-site traffic on the `/` landing page from `(direct) / (none)` and `bing / organic` sources.

[^5]: Python source reference: `google.auth.impersonated_credentials.Credentials` at https://google-auth.readthedocs.io/en/master/reference/google.auth.impersonated_credentials.html. The `source_credentials` parameter is documented as requiring scopes sufficient to call the IAM Credentials API, but the documentation does not call out that `google.auth.default()` returns scopeless credentials by default, which is the source of the misleading error in practice.

[^6]: Git commit `1904c70` in the ads_engine repo on the `synthesized` branch, 2026-04-13 — "Add GA4 service account impersonation path for local dev". Contains the working Python implementation of this pattern.
