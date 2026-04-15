# Follow-Up: Verify UTM Capture Recovery — run on/after 2026-04-14

**Run this on or after 2026-04-14.** If it's already 2026-04-14 or later and this file is still here, run the check and delete the file when done.

## Context

On 2026-04-13 we shipped a fix for the discrete UTM-capture cliff that began on 2026-03-28. Root cause: the Wix → static-site marketing cutover. The new `jotpsych.com` hardcoded 175 "Try for free" CTAs across 34 pages as `https://app.jotpsych.com` with no query string, stripping every Meta/Google ad UTM on click. The old Wix site had a "signup bridge" page that forwarded params; the new static site didn't replicate it.

Fix: a ~40-line snippet in [new_landing_page/site/assets/js/main.js](../new_landing_page/site/assets/js/main.js) that captures UTMs + click IDs to sessionStorage on first arrival and appends them to every `app.jotpsych.com` link on every page. Commit `6fcbf6c` on master of `smartscribe/jotpsych.com`, deployed 2026-04-13 ~12:58 PM.

Full post-mortem: [docs/utm-capture-fix-2026-04-13.md](docs/utm-capture-fix-2026-04-13.md).

## Why this matters

Before the fix, `event_data.utm` on `ACCOUNT_CREATED` landed in 0% of signups from Mar 28 onward vs 20–50% historical. That blocked all Farm-vs-Scale CpFN attribution for the ads_engine. The fix should restore the historical landing rate within 24 hours of live Meta/Google ad traffic flowing through the site.

## The check

Run this against Metabase database 2 (SmartScribe Analytics Supabase). It's the same query the original investigation used to identify the cliff:

```sql
SELECT event_timestamp::date as d,
       COUNT(*) FILTER (WHERE event_data->'utm' IS NOT NULL
                          AND event_data->'utm'::text NOT IN ('null','{}')) as with_utm,
       COUNT(*) as total,
       ROUND(100.0 * COUNT(*) FILTER (WHERE event_data->'utm' IS NOT NULL
                          AND event_data->'utm'::text NOT IN ('null','{}')) / NULLIF(COUNT(*),0), 1) as pct
FROM public.events_with_user
WHERE event_type='ACCOUNT_CREATED'
  AND event_timestamp >= NOW() - INTERVAL '10 days'
GROUP BY 1
ORDER BY 1 DESC
```

Via curl (from ads_engine dir, with `~/.claude/.env` sourced):

```bash
set -a; source ~/.claude/.env; set +a
cat > /tmp/q.json <<'EOF'
{"database":2,"type":"native","native":{"query":"SELECT event_timestamp::date as d, COUNT(*) FILTER (WHERE event_data->'utm' IS NOT NULL AND event_data->'utm'::text NOT IN ('null','{}')) as with_utm, COUNT(*) as total FROM public.events_with_user WHERE event_type='ACCOUNT_CREATED' AND event_timestamp >= NOW() - INTERVAL '10 days' GROUP BY 1 ORDER BY 1 DESC"}}
EOF
curl -s -H "X-API-Key: $METABASE_API_KEY" -H "Content-Type: application/json" \
  -X POST "$METABASE_URL/api/dataset" -d @/tmp/q.json | python3 -m json.tool | head -40
```

## How to interpret the result

**Healthy (expected):** Rows for 2026-04-14 and later show UTMs landing in the 20–50% band. Example: `with_utm=5, total=15, pct=33.3`. This matches the Feb–Mar historical baseline.

**Still broken:** Rows for 2026-04-14 and later show `with_utm=0`. The fix didn't take effect for real traffic. Investigate in this order:

1. **Netlify edge cache.** Re-run the Playwright test from the post-mortem doc. If the live `main.js` on `jotpsych.com/assets/js/main.js` no longer contains `forwardAttribParams`, the cache is serving stale. Purge via Netlify dashboard or re-deploy.
2. **main.js not loading.** Check `curl -sL https://jotpsych.com/assets/js/main.js | grep -c forwardAttribParams` — should be 1. If 0, deploy didn't include the file or there's a path mismatch.
3. **Safari ITP.** Safari's Intelligent Tracking Prevention can clear sessionStorage under some cross-site scenarios. Check whether the missing UTM signups are disproportionately Safari vs Chrome by joining `events_with_user` to a user-agent field (if one exists).
4. **The 2FA pixel issue.** This was flagged as a known separate issue in [CLAUDE.md](CLAUDE.md). It hits conversion tracking, not UTM capture, but worth ruling out.

## When to delete this file

Once the check shows UTMs landing in the 20–50% band for at least one full day (2026-04-14 or later), delete this file and tell Nate the attribution pipeline is healthy again. We can then give a real Farm-vs-Scale CpFN read at the next weekly review.
