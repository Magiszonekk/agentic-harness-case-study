#!/usr/bin/env python3
"""Per-session cost report from the Hermes databases (read-only).

Reads ~/.hermes/state.db and ~/.hermes/profiles/*/state.db, counts tokens and model
calls per session and lists the top N most expensive sessions with "burn" signals
(long context per call, session lifetime, identical repeated tool calls).

Usage: python3 session_report.py [--since 2026-09-25] [--until 2026-10-20] [--top 5] > session-report.md
"""
import argparse, collections, glob, hashlib, json, os, sqlite3, statistics, time

ap = argparse.ArgumentParser()
ap.add_argument("--since", default="2026-09-25")
ap.add_argument("--until", default=None, help="exclusive end date of session start (default: now)")
ap.add_argument("--top", type=int, default=5)
ap.add_argument("--hermes", default=os.path.expanduser("~/.hermes"))
a = ap.parse_args()
t0 = time.mktime(time.strptime(a.since, "%Y-%m-%d"))
t1 = time.mktime(time.strptime(a.until, "%Y-%m-%d")) if a.until else time.time()

def ro(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)

dbs = [os.path.join(a.hermes, "state.db")] + sorted(glob.glob(os.path.join(a.hermes, "profiles/*/state.db")))
rows = []
for db in dbs:
    prof = "default" if db.endswith("/.hermes/state.db") else db.split("/")[-2]
    c = ro(db)
    for r in c.execute(
        """select id, source, started_at, coalesce(last_activity_at, ended_at, started_at), api_call_count,
                  input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, title
           from sessions where started_at >= ? and started_at < ? and api_call_count > 0""", (t0, t1)):
        sid, src, st, last, calls, inp, out, cr, cw, title = r
        tok = (inp or 0) + (out or 0) + (cr or 0) + (cw or 0)
        rows.append(dict(db=db, prof=prof, id=sid, src=src, h=(last - st) / 3600, calls=calls,
                         tok=tok, fresh=(inp or 0) + (out or 0) + (cw or 0), title=(title or "")[:70]))

# After context compaction Hermes keeps copies of old messages in the database (the same
# message_uid and the same tool-call id in several rows), so count unique ids, not rows.
def user_msgs(db, sid):
    return ro(db).execute("select count(distinct coalesce(message_uid, id)) from messages "
                          "where session_id=? and role='user'", (sid,)).fetchone()[0]

def repeats(db, sid):
    sig, seen = collections.Counter(), set()
    for (tc,) in ro(db).execute("select tool_calls from messages where session_id=? and tool_calls is not null", (sid,)):
        try:
            for call in json.loads(tc):
                if call.get("id") in seen:
                    continue
                seen.add(call.get("id"))
                f = call.get("function", call)
                sig[hashlib.md5((str(f.get("name")) + str(f.get("arguments"))).encode()).hexdigest()] += 1
        except Exception:
            pass
    return sum(v - 1 for v in sig.values() if v > 1)

total = sum(r["tok"] for r in rows)
per_call = [r["tok"] / r["calls"] for r in rows]
heavy = [r for r in rows if r["tok"] / r["calls"] > 200e3]
top = sorted(rows, key=lambda r: -r["tok"])[: a.top]

period = f"{a.since} to {a.until}" if a.until else f"since {a.since}"
print(f"# Per-session cost report ({period})\n")
print(f"- sessions that used a model: {len(rows)}, tokens: {total/1e9:.2f}B, "
      f"fresh (not read from cache): {100*sum(r['fresh'] for r in rows)/total:.1f}%")
print(f"- median tokens per call: {statistics.median(per_call)/1e3:.0f}k")
print(f"- top {a.top} sessions: {100*sum(r['tok'] for r in top)/total:.0f}% of all tokens")
print(f"- sessions averaging >200k tokens per call: {len(heavy)}, "
      f"{100*sum(r['tok'] for r in heavy)/total:.0f}% of all tokens\n")
print("| profile | source | tokens | calls | k tokens / call | lifetime | user messages | repeated identical tool calls | title |")
print("|---|---|---|---|---|---|---|---|---|")
for r in top:
    print(f"| {r['prof']} | {r['src']} | {r['tok']/1e6:.0f}M | {r['calls']} | {r['tok']/r['calls']/1e3:.0f} | "
          f"{r['h']:.0f} h | {user_msgs(r['db'], r['id'])} | {repeats(r['db'], r['id'])} | {r['title']} |")
