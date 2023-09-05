#!/usr/bin/python3

import json
import time

import websocket
import sqlite3
from urllib.request import Request, urlopen
from kputil import timeToSeconds


db = sqlite3.connect('karting.db')


def on_open(ws):
    ws.send('{"protocol":"json","version":1}\x1e')
    invocation_id = 0
    for arg in ["KartPalast_timer_rt5",
                "KartPalast_timer_rt4",
                "KartPalast_timer_rt6",
                "KartPalast_timer_rt39",
                "KartPalast_timer_rt22",
                "KartPalast_timer_rt38",
                "KartPalast_current_rt5",
                "KartPalast_current_rt4",
                "KartPalast_current_rt6",
                "KartPalast_current_rt39",
                "KartPalast_current_rt22",
                "KartPalast_current_rt38"]:
        ws.send('{"arguments":["%s"],"invocationId":"%d","streamIds":[],"target":"joinGroup","type":1}\x1e' % (
            arg, invocation_id))
        invocation_id += 1




slava_last_seg1 = 0
running_races = set()
track_ids = {'Raceway 1.00': 5, 'Raceway 2': 4, 'Raceway 3.00': 6, 'Raceway R1-R2': 39, 'Raceway R1 - R3': 22, 'TBO': 38}


def on_message(_, messages):
    for message in messages.split('\x1e'):
      if len(message) == 0:
        continue
      msg = json.loads(message)
      if 'type' in msg:
       if msg['type'] == 1:
            if msg['target'] == 'updateData':
                for m in msg['arguments']:
                    if m['type'] == 'timer':
                        # NotStartedYet = 0
                        # Started = 1
                        # Paused = 2
                        # WaitingForKartsToFinish = 4
                        # Finished = 8
                        # CountDown = 16
                        state = m['data']['state']
                        track_id = int(m['data']['trackId'])
                        if state == 1 or state == 2 or state == 4 or state == 16:
                            running_races.add(track_id)
                        elif state != 8:
                            running_races.discard(track_id)
                    elif m['type'] == 'current':
                        data = m['data']
                        race_id = data['id']
                        track_id = track_ids[data['track'].strip()]
                        if track_id not in running_races and data['finished'] or not data['started']:
                            continue
                        if data['finished']:
                            running_races.discard(track_id)
                        for k in data['karts']:
                            if int(k['kart']) > 100:
                                continue
                            track = data['track'].replace('.00', '')
                            title = data['title'] + ' - ' + data['startTime']

                            bestLap = timeToSeconds(k['bestLap'])
                            bestST = timeToSeconds(k['bestST'])
                            bestST2 = timeToSeconds(k['bestST2'])
                            if bestLap is None and bestST is None and bestST2 is None:
                                continue

                            db.execute(
                                'insert into kart_results (id, raceId, kart, driver, bestLap, bestSegment1, bestSegment2, pit, track, title, timestamp) '
                                'values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) on conflict (id, title) do update set '
                                'bestLap=excluded.bestLap, bestSegment1=excluded.bestSegment1, '
                                'bestSegment2=excluded.bestSegment2, timestamp=excluded.timestamp, driver=excluded.driver where bestLap>excluded.bestLap or bestLap is NULL',
                                (k['id'], race_id, int(k['kart']), k['driver'], bestLap, bestST, bestST2,
                                 k['pit'], track, title, m['timeStamp']))

                            if k['driver'] == 'Slava':
                                global slava_last_seg1
                                if k['lap'] > 0:
                                    db.execute(
                                        'insert into slava_log (id, raceId, position, kart, lap, time, segment1, segment2, bestTime, bestSegment1, bestSegment2, track, title, timestamp) '
                                        'values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) on conflict (id, lap, title) do update set '
                                        'bestTime=excluded.bestTime, bestSegment2=excluded.bestSegment2, time=excluded.time, '
                                        'segment2=excluded.segment2, title=excluded.title, timestamp=excluded.timestamp',
                                        (k['id'], race_id, k['position'], int(k['kart']), k['lap'], timeToSeconds(k['lastLap']),
                                         slava_last_seg1, timeToSeconds(k['lastST2']), bestLap, bestST, bestST2,
                                         track, title, m['timeStamp']))
                                slava_last_seg1 = timeToSeconds(k['lastST'])

                            db.commit()
                    else:
                        print(msg)
            else:
                print(msg)
        elif msg['type'] == 3 and msg['result'] is None:
            pass
        elif msg['type'] == 6:
            pass
        else:
            print(msg)
    else:
        print(msg)


def on_error(_, e):
    raise e


first_start = True


def on_close(_, __, ___):
    global first_start
    if first_start:
        first_start = False
    else:
        time.sleep(10)

    result = json.loads(urlopen('https://www.bubiapp.de/livetiminghub/negotiate?negotiateVersion=1').read()
                        .decode('utf-8'))

    accessToken = result['accessToken']
    url = result['url']
    result = json.loads(urlopen(Request(url.replace('client/', 'client/negotiate'), method='POST',
                                        headers={'Authorization': 'Bearer ' + accessToken})).read().decode('utf-8'))

    ws = websocket.WebSocketApp(
        url.replace('https', 'wss') + '&id=%s&access_token=%s' % (result['connectionId'], accessToken), on_open=on_open,
        on_message=on_message, on_error=on_error, on_close=on_close)
    ws.run_forever()


on_close(None, None, None)
