import os, time, libsql_client
from dotenv import load_dotenv
load_dotenv(r"C:\Users\PC\Desktop\lotto-app\.env")
url = os.environ["TURSO_DATABASE_URL"].replace("libsql://", "https://")
tok = os.environ["TURSO_AUTH_TOKEN"]


def q(sql, *p):
    for _ in range(12):
        try:
            c = libsql_client.create_client_sync(url=url, auth_token=tok)
            r = c.execute(sql, list(p))
            out = [dict(zip(r.columns, row)) for row in r.rows]
            c.close()
            return out
        except Exception as e:
            last = e
            time.sleep(0.4)
    raise RuntimeError(f"gave up ({last!r}): {sql[:70]}")


# lotto_combinations.auto_order_id values that are allocated for round 1241
alloc = q("SELECT auto_order_id, COUNT(*) n FROM lotto_combinations WHERE draw_round=1241 AND auto_order_id IS NOT NULL GROUP BY auto_order_id ORDER BY auto_order_id")
print("### allocated auto_order_id -> combo count (round 1241)")
for a in alloc:
    print("  ", a)

print("\n### member 105 completed order ids")
oids = [o["id"] for o in q("SELECT id FROM auto_orders WHERE member_id=105 AND status='completed'")]
print("  ", sorted(oids))

alloc_ids = {a["auto_order_id"] for a in alloc}
print("\n### member 105 order ids that HAVE allocated combos:", sorted(i for i in oids if i in alloc_ids))
print("### member 105 order ids WITHOUT allocated combos:", sorted(i for i in oids if i not in alloc_ids))

# Is auto_order_id in lotto_combinations maybe pointing to guest_auto_orders.auto_order_id namespace instead?
print("\n### guest_auto_orders.auto_order_id values")
g = q("SELECT auto_order_id FROM guest_auto_orders ORDER BY auto_order_id")
print("  ", [r["auto_order_id"] for r in g])

# marketing_db.allocate uses order_id passed in. Check a sample combo's auto_order_id and draw
print("\n### sample allocated combos round 1241")
for r in q("SELECT id, auto_order_id, num1,num2,num3,num4,num5,num6 FROM lotto_combinations WHERE draw_round=1241 AND auto_order_id IS NOT NULL ORDER BY id LIMIT 8"):
    print("  ", r)
