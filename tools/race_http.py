"""Send two overlapping booking requests to one or two running API instances."""
import concurrent.futures, json, os, time, urllib.error, urllib.request

PORTS=os.getenv("HOTEL_PORTS","5080").split(",")
URLS=[f"http://127.0.0.1:{port.strip()}/reservations" for port in PORTS]
PAYLOADS=[
 {"guestName":"Maya","guestEmail":"maya@example.com","room":"R7","checkIn":"2026-11-12","checkOut":"2026-11-14"},
 {"guestName":"Omar","guestEmail":"omar@example.com","room":"R7","checkIn":"2026-11-12","checkOut":"2026-11-14"},
]
def send(args):
 url,payload=args; req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={"Content-Type":"application/json"},method="POST")
 try:
  with urllib.request.urlopen(req,timeout=15) as r: return r.status,r.read().decode()
 except urllib.error.HTTPError as e: return e.code,e.read().decode()
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 results=list(pool.map(send,[(URLS[i%len(URLS)],PAYLOADS[i]) for i in range(2)]))
for result in results: print(result[0],result[1])
print("Expected invariant: exactly one 201 and one 409.")
