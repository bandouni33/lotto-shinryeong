import os, time, libsql_client
from dotenv import load_dotenv
load_dotenv(r"C:\Users\PC\Desktop\lotto-app\.env")
url = os.environ["TURSO_DATABASE_URL"].replace("libsql://", "https://")
tok = os.environ["TURSO_AUTH_TOKEN"]


def q(sql, *p):
    for _ in range(10):
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


print("### wallet_db.auto_orders schema")
for r in q("PRAGMA table_info(auto_orders)"):
    print("  ", r["name"], r["type"])

print("\n### auto_orders recent 20")
for o in q("SELECT id, member_id, quantity, status, draw_round, combo_count, created_at, completed_at FROM auto_orders ORDER BY id DESC LIMIT 20"):
    print("  ", o)

print("\n### auto_orders by member_id")
for o in q("SELECT member_id, status, COUNT(*) n, GROUP_CONCAT(DISTINCT draw_round) rounds FROM auto_orders GROUP BY member_id, status ORDER BY member_id DESC LIMIT 20"):
    print("  ", o)

print("\n### member 105 completed auto_orders")
for o in q("SELECT id, draw_round, combo_count, status, completed_at FROM auto_orders WHERE member_id=105 ORDER BY id DESC"):
    print("  ", o)

print("\n### lotto_combinations draw_round distribution")
for r in q("SELECT draw_round, COUNT(*) n, SUM(CASE WHEN auto_order_id IS NOT NULL THEN 1 ELSE 0 END) allocated FROM lotto_combinations GROUP BY draw_round ORDER BY draw_round DESC"):
    print("  ", r)

print("\n### wallet_ledger recent for member 105 (auto reasons)")
for r in q("SELECT delta, reason, ref_id, created_at FROM wallet_ledger WHERE member_id=105 ORDER BY id DESC LIMIT 15"):
    print("  ", r)

print("\n### wallets balance member 105")
print("  ", q("SELECT * FROM wallets WHERE member_id=105"))
