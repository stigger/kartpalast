CREATE TABLE IF NOT EXISTS "kart_results" (
"id" INTEGER,
"raceId" INTEGER,
"kart" INTEGER NOT NULL,
"driver" TEXT NOT NULL,
"bestLap" REAL,
"bestSegment1" REAL,
"bestSegment2" REAL,
"pit" TEXT,
"track" TEXT,
"title" TEXT,
"timestamp" INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS "slava_log" (
"id" INTEGER,
"raceId" INTEGER,
"position" INTEGER,
"kart" INTEGER,
"lap" INTEGER,
"time" REAL,
"segment1" REAL,
"segment2" REAL,
"bestTime" REAL,
"bestSegment1" REAL,
"bestSegment2" REAL,
"track" TEXT,
"title" TEXT,
"timestamp" INTEGER
);
CREATE UNIQUE INDEX "id_lap_title" ON "slava_log" ("id", "lap", "title");
CREATE UNIQUE INDEX "id_title" ON "kart_results" ("id", "title");
CREATE INDEX "1" ON "kart_results" ("kart", "bestLap", "track", "timestamp");
CREATE INDEX "2" ON "kart_results" ("raceId");
CREATE INDEX "3" ON "kart_results" ("driver","bestLap","track","timestamp");
CREATE INDEX "4" ON "kart_results" ("bestLap","track","timestamp");
