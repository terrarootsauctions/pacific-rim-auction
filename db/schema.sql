-- Pacific Rim Auction — Autonomous Platform Database Schema
-- Supabase (PostgreSQL) — Self-healing, self-improving backbone

-- ============================================================
-- ENTITIES
-- ============================================================
CREATE TABLE entities (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  type TEXT CHECK (type IN ('llc', 'sole_prop', 'trust', 'corp')),
  ein TEXT,
  state_of_formation TEXT DEFAULT 'HI',
  dcca_cleared BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO entities (name, type, ein, dcca_cleared) VALUES
  ('Pacific Rim Auctions LLC', 'llc', 'SET_EIN_1', TRUE),
  ('Terra Roots Global Realty Solutions LLC', 'llc', 'SET_EIN_2', TRUE);

-- ============================================================
-- USERS / BIDDERS / NOTE HOLDERS
-- ============================================================
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT UNIQUE NOT NULL,
  full_name TEXT,
  phone TEXT,
  country TEXT,
  buyer_type TEXT,
  kyc_status TEXT DEFAULT 'pending' CHECK (kyc_status IN ('pending','verified','flagged','rejected')),
  stripe_customer_id TEXT,
  registered_at TIMESTAMPTZ DEFAULT NOW(),
  last_active TIMESTAMPTZ
);

-- ============================================================
-- PROPERTIES
-- ============================================================
CREATE TABLE properties (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  seller_id UUID REFERENCES users(id),
  entity_id UUID REFERENCES entities(id),
  address TEXT NOT NULL,
  city TEXT, state_region TEXT, country TEXT,
  continent TEXT,
  property_type TEXT,
  bedrooms INT, bathrooms NUMERIC,
  sqft INT,
  year_built INT,
  description TEXT,
  start_bid NUMERIC,
  reserve_price NUMERIC,
  listing_package TEXT CHECK (listing_package IN ('standard','premium','luxury')),
  listing_fee_paid BOOLEAN DEFAULT FALSE,
  stripe_payment_intent TEXT,
  status TEXT DEFAULT 'pending_review' CHECK (status IN (
    'pending_review','approved','active','paused','sold','withdrawn','expired'
  )),
  auction_open TIMESTAMPTZ,
  auction_close TIMESTAMPTZ,
  market_window TEXT,  -- 'Hawaii','US_West','US_East','London','Dubai','Asia_Pacific'
  current_bid NUMERIC DEFAULT 0,
  bid_count INT DEFAULT 0,
  auto_approved BOOLEAN DEFAULT FALSE,
  si_review_notes TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- NOTES (2,500 instruments)
-- ============================================================
CREATE TABLE notes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  holder_id UUID REFERENCES users(id),
  entity_id UUID REFERENCES entities(id),
  note_type TEXT CHECK (note_type IN ('performing','non_performing','seller_financed','commercial','partial')),
  collateral_type TEXT,
  collateral_address TEXT,
  collateral_country TEXT,
  continent TEXT,
  face_value NUMERIC NOT NULL,
  upb NUMERIC NOT NULL,           -- Unpaid Principal Balance
  interest_rate NUMERIC,
  term_months INT,
  remaining_months INT,
  lien_position TEXT DEFAULT 'first',
  ltv_pct NUMERIC,
  payment_status TEXT,
  months_delinquent INT DEFAULT 0,
  listing_fee_paid BOOLEAN DEFAULT FALSE,
  reserve_price NUMERIC,
  status TEXT DEFAULT 'pending_review' CHECK (status IN (
    'pending_review','approved','active','paused','sold','withdrawn','expired'
  )),
  auction_open TIMESTAMPTZ,
  auction_close TIMESTAMPTZ,
  market_window TEXT,
  current_bid NUMERIC DEFAULT 0,
  bid_count INT DEFAULT 0,
  auto_approved BOOLEAN DEFAULT FALSE,
  si_review_notes TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- BIDS
-- ============================================================
CREATE TABLE bids (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  asset_type TEXT CHECK (asset_type IN ('property','note')),
  asset_id UUID NOT NULL,
  bidder_id UUID REFERENCES users(id),
  amount NUMERIC NOT NULL,
  bid_time TIMESTAMPTZ DEFAULT NOW(),
  status TEXT DEFAULT 'active' CHECK (status IN ('active','outbid','winning','retracted','void')),
  ip_address TEXT,
  country TEXT,
  fraud_score NUMERIC DEFAULT 0  -- 0–100, SI-assigned
);

-- ============================================================
-- SI AUDIT LOG (do-no-harm compliance trail)
-- ============================================================
CREATE TABLE si_audit_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type TEXT NOT NULL,
  asset_type TEXT,
  asset_id UUID,
  user_id UUID,
  action_taken TEXT NOT NULL,
  reason TEXT,
  law_reference TEXT,     -- e.g. 'HRS §467E', 'US Bank Secrecy Act'
  jurisdiction TEXT,
  flagged_for_human BOOLEAN DEFAULT FALSE,
  human_reviewed BOOLEAN DEFAULT FALSE,
  human_reviewer_notes TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- FOLLOW-THE-SUN MARKET WINDOWS
-- ============================================================
CREATE TABLE market_windows (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  timezone TEXT NOT NULL,
  open_utc_hour INT,
  close_utc_hour INT,
  primary_region TEXT,
  countries TEXT[]
);

INSERT INTO market_windows (name, timezone, open_utc_hour, close_utc_hour, primary_region) VALUES
  ('Hawaii', 'Pacific/Honolulu', 16, 22, 'Pacific'),
  ('US_West', 'America/Los_Angeles', 16, 24, 'North America'),
  ('US_East', 'America/New_York', 14, 22, 'North America'),
  ('London', 'Europe/London', 8, 17, 'Europe'),
  ('Dubai', 'Asia/Dubai', 6, 14, 'Middle East'),
  ('Asia_Pacific', 'Asia/Singapore', 1, 10, 'Asia-Pacific');

-- ============================================================
-- SELF-HEALING JOBS (SI autonomy triggers)
-- ============================================================
CREATE TABLE si_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_type TEXT NOT NULL,
  target_id UUID,
  target_type TEXT,
  scheduled_at TIMESTAMPTZ,
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending','running','complete','failed','skipped')),
  result JSONB,
  error TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- INDEXES
-- ============================================================
CREATE INDEX idx_properties_status ON properties(status);
CREATE INDEX idx_properties_auction_close ON properties(auction_close);
CREATE INDEX idx_notes_status ON notes(status);
CREATE INDEX idx_notes_type ON notes(note_type);
CREATE INDEX idx_bids_asset ON bids(asset_type, asset_id);
CREATE INDEX idx_si_audit_flagged ON si_audit_log(flagged_for_human) WHERE flagged_for_human = TRUE;
