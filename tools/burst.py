"""Send 30 independent bookings concurrently. Run the API first."""
from __future__ import annotations
import asyncio, sys
from datetime import date, timedelta
import httpx
BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:5080"

async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as client:
        async def book(i):
            start = date(2027, 1, 1) + timedelta(days=i * 2)
            body = {"guestName": f"Guest {i+1}", "guestEmail": f"guest{i+1}@example.com",
                    "room": "R7", "checkIn": start.isoformat(),
                    "checkOut": (start + timedelta(days=1)).isoformat()}
            response = await client.post("/reservations", json=body)
            return response.status_code, response.json()
        results = await asyncio.gather(*(book(i) for i in range(30)))
        print(f"Requests: {len(results)}")
        print(f"Bookings accepted: {sum(status == 201 for status, _ in results)}")
        print(f"HTTP failures: {sum(status != 201 for status, _ in results)}")
        for status, body in results:
            if status != 201: print(status, body)
        stats = (await client.get("/stats")).json()
        print("Queue counters:", stats.get("notifications", "not exposed"))
if __name__ == "__main__":
    asyncio.run(main())
