// Pacific Rim Auction — Autonomous SI Core
// netlify/functions/si-core.js
// Do No Harm · Follow All Laws · Self-Healing · Self-Improving

const { createClient } = require('@supabase/supabase-js');
const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_ROLE_KEY
);

// ── Jurisdictional compliance registry ─────────────────────────────────────
// Expand as platform enters new markets.
const JURISDICTION_RULES = {
  US: { requiresLicensedAgent: true, maxFee: 0.10, currencyCode: 'USD', lawRef: 'US RESPA / State RE Law' },
  AU: { requiresLicensedAgent: true, maxFee: 0.05, currencyCode: 'AUD', lawRef: 'National Consumer Credit Protection Act' },
  JP: { requiresLicensedAgent: true, maxFee: 0.03, currencyCode: 'JPY', lawRef: 'Real Estate Transaction Law' },
  SG: { requiresLicensedAgent: false, maxFee: 0.02, currencyCode: 'SGD', lawRef: 'Estate Agents Act' },
  DEFAULT: { requiresLicensedAgent: false, maxFee: 0.10, currencyCode: 'USD', lawRef: 'Applicable local law' },
};

// ── Do-No-Harm checkers ─────────────────────────────────────────────────────
const HARM_RULES = [
  { id: 'no_undisclosed_fees',     check: (a) => a.listing_fee_paid === true },
  { id: 'no_reserve_below_debt',   check: (a) => !a.reserve_price || a.reserve_price >= (a.upb || 0) * 0.5 },
  { id: 'no_active_litigation',    check: (a) => !a.metadata?.litigation_flag },
  { id: 'no_title_defect',         check: (a) => !a.metadata?.title_defect_flag },
];

function runHarmChecks(asset) {
  const failures = HARM_RULES.filter(r => !r.check(asset)).map(r => r.id);
  return { passed: failures.length === 0, failures };
}

// ── Auto-approval logic (SI decides) ───────────────────────────────────────
async function autoReviewListing(assetType, assetId) {
  const table = assetType === 'property' ? 'properties' : 'notes';
  const { data: asset } = await supabase.from(table).select('*').eq('id', assetId).single();
  if (!asset) return { approved: false, reason: 'Asset not found' };

  const harmCheck = runHarmChecks(asset);
  const countryCode = (asset.collateral_country || asset.country || 'US').toUpperCase().slice(0, 2);
  const jurisdiction = JURISDICTION_RULES[countryCode] || JURISDICTION_RULES.DEFAULT;

  if (!harmCheck.passed) {
    await logSIAction({ assetType, assetId, action: 'FLAGGED_FOR_REVIEW', reason: `Harm checks failed: ${harmCheck.failures.join(', ')}`, law: jurisdiction.lawRef, flaggedForHuman: true });
    await supabase.from(table).update({ status: 'pending_review', si_review_notes: `SI flagged: ${harmCheck.failures.join(', ')}` }).eq('id', assetId);
    return { approved: false, flaggedForHuman: true, reason: harmCheck.failures };
  }

  // Calculate market window based on continent
  const marketWindow = getMarketWindow(asset.continent || 'NA');
  const auctionOpen = nextMarketOpen(marketWindow);
  const auctionClose = new Date(auctionOpen.getTime() + 30 * 24 * 60 * 60 * 1000); // 30 days

  await supabase.from(table).update({
    status: 'approved',
    auto_approved: true,
    auction_open: auctionOpen.toISOString(),
    auction_close: auctionClose.toISOString(),
    market_window: marketWindow,
    si_review_notes: `SI auto-approved. Jurisdiction: ${countryCode}. Market window: ${marketWindow}.`
  }).eq('id', assetId);

  await logSIAction({ assetType, assetId, action: 'AUTO_APPROVED', reason: `All harm checks passed. Market: ${marketWindow}.`, law: jurisdiction.lawRef, flaggedForHuman: false });

  return { approved: true, marketWindow, auctionOpen, auctionClose };
}

// ── Follow-the-Sun market window assignment ─────────────────────────────────
function getMarketWindow(continent) {
  const map = {
    'NA': 'US_West', 'North America': 'US_West',
    'EU': 'London',  'Europe': 'London',
    'AS': 'Asia_Pacific', 'Asia': 'Asia_Pacific', 'Asia-Pacific': 'Asia_Pacific',
    'OC': 'Asia_Pacific', 'Oceania': 'Asia_Pacific',
    'SA': 'US_East', 'South America': 'US_East',
    'AF': 'Dubai',   'Africa': 'Dubai',
    'ME': 'Dubai',   'Middle East': 'Dubai',
    'HI': 'Hawaii',  'Pacific': 'Hawaii',
  };
  return map[continent] || 'US_West';
}

function nextMarketOpen(window) {
  const UTC_OPENS = { Hawaii: 16, US_West: 16, US_East: 14, London: 8, Dubai: 6, Asia_Pacific: 1 };
  const now = new Date();
  const openHour = UTC_OPENS[window] || 16;
  const next = new Date(now);
  next.setUTCHours(openHour, 0, 0, 0);
  if (next <= now) next.setUTCDate(next.getUTCDate() + 1);
  return next;
}

// ── Audit logging ───────────────────────────────────────────────────────────
async function logSIAction({ assetType, assetId, action, reason, law, flaggedForHuman }) {
  await supabase.from('si_audit_log').insert({
    event_type: action,
    asset_type: assetType,
    asset_id: assetId,
    action_taken: action,
    reason,
    law_reference: law,
    flagged_for_human: flaggedForHuman || false,
  });
}

// ── Stripe webhook handler ──────────────────────────────────────────────────
async function handleStripeWebhook(rawBody, signature) {
  let event;
  try {
    event = stripe.webhooks.constructEvent(rawBody, signature, process.env.STRIPE_WEBHOOK_SECRET);
  } catch (e) {
    return { statusCode: 400, body: `Webhook signature failure: ${e.message}` };
  }

  if (event.type === 'checkout.session.completed') {
    const session = event.data.object;
    const { package: pkg, property_address, seller_name } = session.metadata;

    // Mark listing fee paid and trigger SI auto-review
    // (In production: look up asset by session ID, update, then call autoReviewListing)
    await logSIAction({
      assetType: 'property',
      assetId: session.metadata.asset_id || 'pending',
      action: 'PAYMENT_CONFIRMED',
      reason: `Stripe checkout completed for ${seller_name} — ${property_address} — ${pkg} package`,
      law: 'Stripe Compliance',
      flaggedForHuman: false,
    });
  }

  return { statusCode: 200, body: JSON.stringify({ received: true }) };
}

// ── Self-healing: scan for stale/expired listings ──────────────────────────
async function selfHealExpiredListings() {
  const now = new Date().toISOString();

  const { data: expired } = await supabase
    .from('properties')
    .select('id')
    .eq('status', 'active')
    .lt('auction_close', now);

  for (const prop of (expired || [])) {
    await supabase.from('properties').update({ status: 'expired' }).eq('id', prop.id);
    await logSIAction({ assetType: 'property', assetId: prop.id, action: 'AUTO_EXPIRED', reason: 'Auction close time passed', law: 'Platform rules', flaggedForHuman: false });
  }

  const { data: expiredNotes } = await supabase
    .from('notes')
    .select('id')
    .eq('status', 'active')
    .lt('auction_close', now);

  for (const note of (expiredNotes || [])) {
    await supabase.from('notes').update({ status: 'expired' }).eq('id', note.id);
    await logSIAction({ assetType: 'note', assetId: note.id, action: 'AUTO_EXPIRED', reason: 'Auction close time passed', law: 'Platform rules', flaggedForHuman: false });
  }

  return { healed: (expired?.length || 0) + (expiredNotes?.length || 0) };
}

// ── Lambda entry ────────────────────────────────────────────────────────────
exports.handler = async (event) => {
  const path = event.path || '';

  if (path.includes('stripe-webhook')) {
    return handleStripeWebhook(event.body, event.headers['stripe-signature']);
  }

  if (path.includes('self-heal')) {
    const result = await selfHealExpiredListings();
    return { statusCode: 200, body: JSON.stringify(result) };
  }

  if (path.includes('review-listing')) {
    const { assetType, assetId } = JSON.parse(event.body || '{}');
    const result = await autoReviewListing(assetType, assetId);
    return { statusCode: 200, body: JSON.stringify(result) };
  }

  return { statusCode: 404, body: 'Unknown SI route' };
};
