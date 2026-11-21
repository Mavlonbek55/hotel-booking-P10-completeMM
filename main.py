"""P09 hotel booking API and concurrency demonstrations."""
from __future__ import annotations
import os, sys, threading, time
from contextlib import contextmanager
from datetime import date
import redis
import uvicorn
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from hotel_booking.api import SearchStats, create_app
from hotel_booking.api_cache import AvailabilityCache
from hotel_booking.notifications.internal import EmailNotificationSender, QueuedNotificationSender
from hotel_booking.reservations import BookingService, DateRange, Guest
from hotel_booking.reservations.internal import InMemoryReservationStore, PostgresReservationStore
from hotel_booking.rooms import Room
from hotel_booking.rooms.internal import InMemoryRoomCatalog, PostgresRoomCatalog

R7, R8 = Room("R7", "Standard"), Room("R8", "Deluxe")
MAYA, OMAR = Guest("Maya", "maya@example.com"), Guest("Omar", "omar@example.com")
CATALOG = InMemoryRoomCatalog([R7, R8])

def nov(a=12,b=14): return DateRange(date(2026,11,a), date(2026,11,b))

def run_race():
    store=InMemoryReservationStore(); delay=float(os.getenv("HOTEL_SLOW_STEP","0.5"))
    service=BookingService(CATALOG.all(),store,EmailNotificationSender(),slow_step_seconds=delay)
    results={}
    def book(name,guest): results[name]=service.reserve(guest,R7,nov())
    t1=threading.Thread(target=book,args=("Maya",MAYA)); t2=threading.Thread(target=book,args=("Omar",OMAR))
    t1.start(); time.sleep(0.1); t2.start(); t1.join(); t2.join()
    print(f"Maya: {results['Maya']}"); print(f"Omar: {results['Omar']}")
    print(f"Confirmed overlapping reservations: {store.count_confirmed(R7,nov())}")
    print("Double booking reproduced." if store.count_confirmed(R7,nov())>1 else "Only one guest has R7.")

def run_api():
    db_port=os.getenv("HOTEL_DB_PORT","5432"); port=int(os.getenv("HOTEL_PORT","5080"))
    engine=create_engine(f"postgresql+psycopg://hotel:hotel@localhost:{db_port}/hotel", pool_pre_ping=True)
    rooms=PostgresRoomCatalog(engine).all()
    email=EmailNotificationSender(send_seconds=float(os.getenv("HOTEL_EMAIL_SECONDS","0")))
    notifications=QueuedNotificationSender(email, capacity=10)
    cache_enabled=os.getenv("HOTEL_CACHE_ENABLED","1") != "0"
    cache=AvailabilityCache(redis.Redis(host="localhost",port=int(os.getenv("HOTEL_REDIS_PORT","6379")),decode_responses=True)) if cache_enabled else None
    stats=SearchStats()
    @contextmanager
    def unit_of_work():
        with Session(engine) as session:
            store=PostgresReservationStore(session,rooms)
            try:
                yield BookingService(
                    rooms, store, notifications,
                    slow_step_seconds=float(os.getenv("HOTEL_SLOW_STEP","0")),
                    commit_after_save=store.save_changes,
                )
                store.save_changes()
            except Exception:
                session.rollback(); raise
    uvicorn.run(create_app(rooms,unit_of_work,cache,stats,notifications),host="127.0.0.1",port=port)

if __name__=="__main__":
    if "--race" in sys.argv: run_race()
    else: run_api()
