#!/usr/bin/env python3
"""Raport kosztu per sesja z baz Hermesa (read-only).

Czyta ~/.hermes/state.db i ~/.hermes/profiles/*/state.db, liczy tokeny i wywołania
per sesja, pokazuje top N najdroższych z sygnałami „palenia” (długi kontekst na
wywołanie, czas życia sesji, identyczne powtórzone wywołania narzędzi).

Użycie: python3 raport_sesji.py [--od 2026-09-25] [--top 5] > raport.md
"""
import argparse, collections, glob, hashlib, json, os, sqlite3, statistics, time

ap = argparse.ArgumentParser()
ap.add_argument("--od", default="2026-09-25")
ap.add_argument("--top", type=int, default=5)
ap.add_argument("--hermes", default=os.path.expanduser("~/.hermes"))
a = ap.parse_args()
t0 = time.mktime(time.strptime(a.od, "%Y-%m-%d"))

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
           from sessions where started_at >= ? and api_call_count > 0""", (t0,)):
        sid, src, st, last, calls, inp, out, cr, cw, title = r
        tok = (inp or 0) + (out or 0) + (cr or 0) + (cw or 0)
        rows.append(dict(db=db, prof=prof, id=sid, src=src, h=(last - st) / 3600, calls=calls,
                         tok=tok, fresh=(inp or 0) + (out or 0) + (cw or 0), title=(title or "")[:70]))

# Po kompakcji kontekstu Hermes trzyma w bazie kopie starych wiadomości (to samo message_uid
# i to samo id wywołania narzędzia w kilku wierszach) — liczymy unikalne, nie wiersze.
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

print(f"# Raport kosztu per sesja (od {a.od})\n")
print(f"- sesje z użyciem modelu: {len(rows)}, tokeny: {total/1e9:.2f} mld, "
      f"nowe (bez odczytu z cache): {100*sum(r['fresh'] for r in rows)/total:.1f}%")
print(f"- mediana tokenów na wywołanie: {statistics.median(per_call)/1e3:.0f} tys.")
print(f"- top {a.top} sesji: {100*sum(r['tok'] for r in top)/total:.0f}% wszystkich tokenów")
print(f"- sesje ze średnio >200 tys. tokenów na wywołanie: {len(heavy)}, "
      f"{100*sum(r['tok'] for r in heavy)/total:.0f}% wszystkich tokenów\n")
print("| profil | źródło | tokeny | wywołania | tys. tok./wywołanie | czas życia | wiadomości usera | powtórzone identyczne wywołania narzędzi | tytuł |")
print("|---|---|---|---|---|---|---|---|---|")
for r in top:
    print(f"| {r['prof']} | {r['src']} | {r['tok']/1e6:.0f} mln | {r['calls']} | {r['tok']/r['calls']/1e3:.0f} | "
          f"{r['h']:.0f} h | {user_msgs(r['db'], r['id'])} | {repeats(r['db'], r['id'])} | {r['title']} |")
