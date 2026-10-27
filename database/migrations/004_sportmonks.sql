-- 004_sportmonks.sql — Sportmonks player-match statistics (30 leagues, scouting).
--
-- Kept in its own sm_* tables with Sportmonks' own ids: these are a different
-- provider with different stat definitions (a Sportmonks "duel" is not a Wyscout
-- duel), so they are never mixed into match_instances / player_events. Linking a
-- Sportmonks player to our players table is a later, explicit step
-- (player_external_ids with source = 'sportmonks').
--
-- Stats are stored as jsonb keyed by Sportmonks type_id (stable integers);
-- sm_types gives each id its name. A new stat appearing in the feed therefore
-- needs no schema change.

CREATE TABLE IF NOT EXISTS sm_types (
    type_id         integer PRIMARY KEY,
    name            text NOT NULL,
    code            text,
    developer_name  text,
    model_type      text,
    stat_group      text
);

CREATE TABLE IF NOT EXISTS sm_seasons (
    season_id    integer PRIMARY KEY,
    league_id    integer NOT NULL,
    league_name  text NOT NULL,
    country      text,
    season_name  text NOT NULL,
    starting_at  date,
    ending_at    date,
    is_current   boolean
);

CREATE TABLE IF NOT EXISTS sm_fixtures (
    fixture_id     bigint PRIMARY KEY,
    season_id      integer NOT NULL REFERENCES sm_seasons(season_id),
    starting_at    timestamptz,                 -- UTC, as Sportmonks sends it
    home_team_id   integer,
    home_team      text,
    away_team_id   integer,
    away_team      text,
    home_goals     smallint,
    away_goals     smallint,
    state_id       smallint,                    -- 5 = finished
    lineups_loaded boolean NOT NULL DEFAULT false,
    loaded_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sm_fixtures_season ON sm_fixtures(season_id);

CREATE TABLE IF NOT EXISTS sm_players (
    player_id             integer PRIMARY KEY,
    name                  text NOT NULL,
    display_name          text,
    date_of_birth         date,
    height_cm             smallint,
    weight_kg             smallint,
    nationality_id        integer,
    position_id           integer,             -- -> sm_types (GK / DEF / MID / ATT)
    detailed_position_id  integer,             -- -> sm_types (Centre Back, Left Back, ...)
    updated_at            timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sm_player_match (
    fixture_id          bigint  NOT NULL REFERENCES sm_fixtures(fixture_id) ON DELETE CASCADE,
    player_id           integer NOT NULL REFERENCES sm_players(player_id),
    team_id             integer NOT NULL,
    starter             boolean NOT NULL,      -- lineup type 11 = starting XI, 12 = bench
    position_id         integer,               -- position in THIS match
    formation_field     text,                  -- e.g. '2:3' (row:column in the formation)
    jersey_number       smallint,
    minutes             smallint,              -- copied out of stats for fast filtering
    stats               jsonb NOT NULL DEFAULT '{}'::jsonb,   -- {type_id: value}
    PRIMARY KEY (fixture_id, player_id)
);
CREATE INDEX IF NOT EXISTS idx_sm_pm_player ON sm_player_match(player_id);
CREATE INDEX IF NOT EXISTS idx_sm_pm_stats ON sm_player_match USING gin (stats);
