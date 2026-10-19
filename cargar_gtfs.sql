-- identificadores textuales, secuencias numéricas y horas GTFS conservadas como texto
CREATE TABLE __ESQUEMA__.gtfs_stops (
    stop_id text PRIMARY KEY, stop_code text, stop_name text,
    stop_lat double precision CHECK (stop_lat BETWEEN -90 AND 90),
    stop_lon double precision CHECK (stop_lon BETWEEN -180 AND 180),
    stop_url text, wheelchair_boarding integer,
    location_type integer CHECK (location_type BETWEEN 0 AND 4),
    parent_station text REFERENCES __ESQUEMA__.gtfs_stops(stop_id), level_id text,
    CHECK (COALESCE(location_type,0) IN (3,4) OR (stop_lat IS NOT NULL AND stop_lon IS NOT NULL))
);
CREATE TABLE __ESQUEMA__.gtfs_shapes (
    shape_id text NOT NULL,
    shape_pt_lat double precision NOT NULL CHECK (shape_pt_lat BETWEEN -90 AND 90),
    shape_pt_lon double precision NOT NULL CHECK (shape_pt_lon BETWEEN -180 AND 180),
    shape_pt_sequence integer NOT NULL CHECK (shape_pt_sequence >= 0),
    PRIMARY KEY (shape_id,shape_pt_sequence)
);
CREATE TABLE __ESQUEMA__.gtfs_routes (
    route_id text PRIMARY KEY, agency_id text, route_short_name text, route_long_name text,
    route_desc text, route_type integer NOT NULL, route_url text,
    route_color text, route_text_color text
);
CREATE TABLE __ESQUEMA__.gtfs_calendar (
    service_id text PRIMARY KEY,
    monday integer NOT NULL CHECK(monday IN (0,1)),
    tuesday integer NOT NULL CHECK(tuesday IN (0,1)),
    wednesday integer NOT NULL CHECK(wednesday IN (0,1)),
    thursday integer NOT NULL CHECK(thursday IN (0,1)),
    friday integer NOT NULL CHECK(friday IN (0,1)),
    saturday integer NOT NULL CHECK(saturday IN (0,1)),
    sunday integer NOT NULL CHECK(sunday IN (0,1)),
    start_date date NOT NULL,end_date date NOT NULL CHECK(end_date>=start_date)
);
CREATE TABLE __ESQUEMA__.gtfs_calendar_dates (
    service_id text REFERENCES __ESQUEMA__.gtfs_calendar(service_id),
    date date NOT NULL,exception_type integer NOT NULL CHECK(exception_type IN (1,2)),
    PRIMARY KEY(service_id,date)
);
CREATE INDEX idx_gtfs_calendar_dates_date ON __ESQUEMA__.gtfs_calendar_dates(date);
CREATE TABLE __ESQUEMA__.gtfs_trips (
    route_id text NOT NULL REFERENCES __ESQUEMA__.gtfs_routes(route_id),
    service_id text NOT NULL REFERENCES __ESQUEMA__.gtfs_calendar(service_id),
    trip_id text PRIMARY KEY, trip_headsign text,
    direction_id integer, shape_id text, trip_short_name text,
    wheelchair_accessible integer, bikes_allowed integer
);
CREATE TABLE __ESQUEMA__.gtfs_stop_times (
    trip_id text NOT NULL REFERENCES __ESQUEMA__.gtfs_trips(trip_id),
    arrival_time text, departure_time text,
    stop_id text NOT NULL REFERENCES __ESQUEMA__.gtfs_stops(stop_id),
    stop_sequence integer NOT NULL CHECK (stop_sequence >= 0),
    pickup_type integer, drop_off_type integer, timepoint integer,
    PRIMARY KEY (trip_id,stop_sequence)
);
CREATE TABLE __ESQUEMA__.gtfs_frequencies (
    trip_id text REFERENCES __ESQUEMA__.gtfs_trips(trip_id),
    start_time text NOT NULL CHECK(start_time ~ '^[0-9]{2,}:[0-5][0-9]:[0-5][0-9]$'),
    end_time text NOT NULL CHECK(end_time ~ '^[0-9]{2,}:[0-5][0-9]:[0-5][0-9]$'),
    headway_secs integer NOT NULL CHECK(headway_secs>0),
    exact_times integer CHECK(exact_times IN (0,1)),
    PRIMARY KEY(trip_id,start_time)
);
