import asyncio
from datetime import datetime, timedelta
from enum import Enum
from hashlib import sha1
from icalendar import Calendar, Event
import time
import aiohttp
import sqlite3
import json
import pytz
import os
import urllib.parse

# use datetime.fromisoformat when python 3.7+
from kputil import fromisoformat, timeToString


tz = pytz.timezone('Europe/Berlin')


class Raceways(Enum):
    raceway1 = (5, 'RW1', urllib.parse.quote('Raceway 1'))
    raceway2 = (4, 'RW2', urllib.parse.quote('Raceway 2'))
    raceway3 = (6, 'RW3', urllib.parse.quote('Raceway 3'))
    raceway1_2 = (39, 'RW1&2', urllib.parse.quote('Raceway 1 & 2'))
    raceway1_3 = (22, 'RW1&3', urllib.parse.quote('Raceway 1 & 3'))
    tbo = (38, 'TBO', urllib.parse.quote('TBO '))


calendarEvents = []
lastUpdate = 0


async def calendar(force_reload=True):
    async with aiohttp.ClientSession() as session:
        cal = Calendar()
        cal.add('version', '2.0')

        global calendarEvents
        global lastUpdate
        if force_reload or lastUpdate + 60 < time.time():
            lastUpdate = time.time()
            from_date = datetime.utcnow().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
            to_date = from_date + timedelta(days=10)
            from_date = from_date.isoformat()
            to_date = to_date.isoformat()

            async def req(session, rw):
                data = {'from': from_date, 'to': to_date, 'facilityId': rw.value[0], 'provider': 'KartPalast'}
                async with session.post('https://www.bubiapp.de/api/booking/calendarEvents', json=data) as resp:
                    return rw, await resp.json()

            tasks = []
            for rw in [Raceways.raceway1, Raceways.raceway2, Raceways.raceway3, Raceways.raceway1_2, Raceways.tbo]:
                tasks.append(req(session, rw))
            calendarEvents = await asyncio.gather(*tasks)

        for (rw, data) in calendarEvents:
            for d in data:
                if d['total'] == 0:
                    continue
                start_date_time = fromisoformat(d['startDateTime']).replace(tzinfo=tz)
                end_date_time = fromisoformat(d['endDateTime']).replace(tzinfo=tz)
                hour = start_date_time.hour

                event = Event()
                event.add('summary', "%s (%s/%s) - %s" % (rw.value[1], d['booked'], d['total'], d['title']))
                event.add('dtstart', start_date_time)
                event.add('dtend', end_date_time)
                event.add('dtstamp', datetime.utcnow())
                event.add('uid', sha1((d['productId'] + d['id'] + d['startDateTime'] + d['facilityId']).encode('utf-8')).hexdigest())
                description = '%s/%s gebucht, %s verfügbar' % (d['booked'], d['total'], d['available'])
                if d['isExclusive'] or not d['bookableOnline'] or d['available'] == 0:
                    event.add('status', 'CANCELLED')
                else:
                    description += '\nhttps://kartpalast.de/eventkalender/#/online-calendar/search?d=%s&f=%d&t=%d&r=%s' % (
                        start_date_time.strftime("%d%m%Y"), hour, hour + 1, rw.value[2])
                event.add('description', description)
                cal.add_component(event)
        return cal.to_ical()


if os.path.exists('/Volumes/storage/.karting.db'):
    db = sqlite3.connect('/Volumes/storage/.karting.db')
elif os.path.exists('/mnt/storage/.karting.db'):
    db = sqlite3.connect('/mnt/storage/.karting.db')
else:
    db = sqlite3.connect('karting.db')


def retrieve_stats(query_executor, data_extractor, dedupe_index=0, sort=False, limit=10):
    stats = []
    for rw in ['Raceway 1', 'Raceway 2', 'Raceway 3', 'Raceway R1-R2', 'Raceway R1 - R3', 'TBO']:
        results = query_executor(rw)

        dedupe = set()
        items = []
        for result in results:
            (id_, timestamp, bestLap) = result[:3]

            if result[dedupe_index] in dedupe:
                continue
            dedupe.add(result[dedupe_index])

            date = datetime.fromtimestamp(timestamp / 1000, tz).strftime('%d.%m.%Y')  # '%d.%m.%Y %H:%M'
            item = {
                'id': id_,
                'date': date,
                'time': timeToString(bestLap),
            }
            item.update(data_extractor(result[3:]))
            items.append(item)
            if len(items) == limit:
                break
        if len(items) > 0:
            stats.append({'raceway': rw.replace(' - ', '-'), 'data': items})
    if sort:
        stats = sorted(stats, key=lambda x: -len(x['data']))
    return json.dumps(stats).encode('utf-8')


def kart_stats(kart):
    if not kart.strip():
        return '[]'.encode('utf-8')
    kart = int(kart)
    if kart < 1 or kart > 90:
        return '[]'.encode('utf-8')

    def query(rw):
        return db.execute(
            'select id, timestamp, bestLap, driver from kart_results where kart=? and bestLap is not null and '
            'track=? and timestamp > ? order by bestLap limit 0, 50',
            (kart, rw, int(time.time() * 1000) - 45 * 86400_000)).fetchall()

    def extract(result):
        return {'driver': result[0]}

    return retrieve_stats(query, extract)


def driver_stats(driver):
    def query(rw):
        return db.execute(
            'select id, timestamp, bestLap, kart, bestSegment1, bestSegment2 from kart_results where driver=? '
            'and bestLap is not null and track=? order by bestLap limit 0, 50', (driver, rw)).fetchall()

    def extract(result):
        (kart, bestSegment1, bestSegment2) = result
        return {
            'kart': kart,
            'bestSegment1': timeToString(bestSegment1),
            'bestSegment2': timeToString(bestSegment2),
        }

    return retrieve_stats(query, extract, sort=True, limit=20)


def raceways_stats():
    def query(rw):
        return db.execute(
            'select id, timestamp, bestLap, kart, driver from kart_results where bestLap is not null and track=? and timestamp>=?'
            'order by bestLap limit 0, 50', (rw, int(time.time() * 1000) - 45 * 86400_000)).fetchall()

    def extract(result):
        (kart, driver) = result
        return {'kart': kart, 'driver': driver}

    return retrieve_stats(query, extract, dedupe_index=4, limit=15)


def application(env, start_response):
    # todo use asyncio.run when python 3.7+
    loop = asyncio.get_event_loop()
    path = env['PATH_INFO']
    response = None

    if path == '/kartpalast.ics':
        cal = loop.run_until_complete(calendar(env['QUERY_STRING'] == 'forceReload'))
        start_response('200 OK', [('Content-Type', 'text/calendar; charset=utf-8')])
        return [cal]
    elif path.startswith('/kartpalast/kart/'):
        kart = path.split('/')[-1]
        response = kart_stats(kart)
    elif path.startswith('/kartpalast/driver/'):
        driver = urllib.parse.unquote(path.split('/')[-1])
        response = driver_stats(driver)
    elif path == '/kartpalast/raceways':
        response = raceways_stats()

    if response:
        start_response('200 OK', [
            ('Content-Type', 'text/json; charset=utf-8'),
            ('Access-Control-Allow-Origin', '*'),
            ('Cache-Control', 'no-store'),
        ])
        return [response]

    start_response('404 Not Found', [])
    return ['Not Found'.encode('utf-8')]


if __name__ == '__main__':
    print(asyncio.run(calendar()).decode('utf-8'))
