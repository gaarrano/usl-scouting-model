-- 005_sm_us_link.sql — US eligibility signals for Sportmonks players (domestic-slot scouting).
-- country_id    = country of BIRTH (Sportmonks docs). Born in the US => US citizen by birth.
-- us_link       = 'born_us' | 'usa_national_team' | NULL, filled by scouting/sm_us_eligible.py
ALTER TABLE sm_players ADD COLUMN IF NOT EXISTS country_id integer;
ALTER TABLE sm_players ADD COLUMN IF NOT EXISTS us_link text;
