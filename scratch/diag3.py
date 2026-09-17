import os, time, libsql_client
from dotenv import load_dotenv
load_dotenv(r"C:\Users\PC\Desktop\lotto-app\.env")
url = os.environ["TURSO_DATABASE_URL"].replace("libsql://", "https://")
tok = os.environ["TURSO_AUTH_TOKEN"]


def q(sql, *p):
    for attempt in range(10):
        try:
            c = libsql_client.create_client_sync(url=url, auth_token=tok)
            r = c.execute(sql, list(p))
            out = [dict(zip(r.columns, row)) for row in r.rows]
            c.close()
            return out
        except Exception as e:
            last = e
            time.sleep(0.5)
    raise RuntimeError(f"gave up ({last!r}): {sql[:70]}")


print("### guest_auto_orders recent 15")
for o in q("SELECT id, substr(guest_id,1,12) gid, auto_order_id, draw_round, combo_count, created_at FROM guest_auto_orders ORDER BY id DESC LIMIT 15"):
    print("  ", o)

print("\n### draw_round distribution in guest_auto_orders")
print("  ", q("SELECT draw_round, COUNT(*) n FROM guest_auto_orders GROUP BY draw_round ORDER BY draw_round DESC"))

print("\n### NULL auto_order_id in guest_auto_orders")
print("  ", q("SELECT COUNT(*) n FROM guest_auto_orders WHERE auto_order_id IS NULL"))

print("\n### latest lotto_combinations draw_round")
print("  ", q("SELECT MAX(draw_round) mx FROM lotto_combinations"))

print("\n### member 105: all linked gids, order/combo counts")
allg = [r["guest_id"] for r in q("SELECT guest_id FROM guest_member_links WHERE member_id=105")]
print(f"  {len(allg)} linked gids")
ph = ",".join("?" * len(allg))
print("  guest_auto_orders total:", q(f"SELECT COUNT(*) n, GROUP_CONCAT(DISTINCT draw_round) r FROM guest_auto_orders WHERE guest_id IN ({ph})", *allg))
print("  guest_generated_combos total:", q(f"SELECT COUNT(*) n, GROUP_CONCAT(DISTINCT draw_round) r FROM guest_generated_combos WHERE guest_id IN ({ph})", *allg))

print("\n### which linked gids actually have auto orders")
for g in allg:
    n = q("SELECT COUNT(*) n FROM guest_auto_orders WHERE guest_id=?", g)[0]["n"]
    if n:
        print(f"   {g}  orders={n}")

print("\n### _diag_guest_id_log branch counts last 200")
try:
    rows = q("SELECT branch FROM _diag_guest_id_log ORDER BY id DESC LIMIT 200")
    from collections import Counter
    print("  ", Counter(r["branch"] for r in rows))
    print("  recent 12:")
    for d in q("SELECT branch, substr(guest_id,1,8) gid, page, created_at FROM _diag_guest_id_log ORDER BY id DESC LIMIT 12"):
        print("   ", d)
except Exception as e:
    print("  none:", e)
