# 🌊 Pacific Rim Auction — Deployment Guide

## Files in this package
- `index.html` — Homepage
- `listings.html` — Live auctions grid
- `list-property.html` — Seller listing form + Stripe checkout
- `register.html` — Buyer registration
- `auction.html` — Individual auction detail (coming next)
- `listing-success.html` — Post-payment confirmation
- `css/style.css` — Full stylesheet
- `js/main.js` — Auction logic, countdowns, listings
- `netlify/functions/create-checkout-session.js` — Stripe backend
- `netlify.toml` — Netlify configuration
- `package.json` — Node dependencies

---

## 🚀 DEPLOY IN 10 MINUTES (Netlify — Free)

### Step 1: Create Netlify Account
1. Go to https://netlify.com → Sign up free
2. Click "Add new site" → "Deploy manually"

### Step 2: Deploy the Site
1. Unzip the downloaded package
2. Drag the entire `pacificrim-platform` folder into Netlify's drop zone
3. Site goes live instantly at a `.netlify.app` URL

### Step 3: Connect Your Stripe
1. In Netlify Dashboard → Site Settings → Environment Variables
2. Add: `STRIPE_SECRET_KEY` = your Stripe secret key (starts with `sk_live_...`)
3. Add: `SITE_URL` = your site URL (e.g. `https://pacificrimauction.netlify.app`)

### Step 4: Connect Your Domain
1. Netlify → Domain Management → Add custom domain
2. Enter: `pacificrimauction.com`
3. Update your domain's DNS nameservers to Netlify's (they'll show you exactly what to set)

---

## 💳 STRIPE SETUP (You said Stripe is already live)

In your Stripe Dashboard:
1. Go to Products → Create 3 products:
   - "Standard Listing Package" — $200 one-time
   - "Premium Listing Package" — $500 one-time
   - "Luxury White-Glove Package" — $1,000 one-time
2. Copy each Price ID (starts with `price_...`)
3. In `list-property.html`, replace the 3 `REPLACE_WITH_STRIPE_PRICE_ID_*` placeholders

---

## 🌐 2,500 NOTES — "Follow the Sun" Auction Scheduling

To set up time-zone-aware auction scheduling (First In, First Out / Follow the Sun):
- Each listing can have a scheduled open/close time
- The platform auto-converts to local time for each visitor
- Phase 1: Hawaii → US Pacific → Australia → Japan → Singapore
- This is ready to be wired into a backend (Supabase or Firebase recommended)

---

## 🏗️ RECOMMENDED TECH STACK FOR FULL PLATFORM

| Layer | Service | Why |
|-------|---------|-----|
| Hosting | Netlify | Free, fast, instant deploy |
| Database | Supabase | Real-time bidding, free tier |
| Auth | Supabase Auth | Users, sessions, KYC hooks |
| Payments | Stripe (you have it) | Listing fees + escrow |
| Email | Resend or SendGrid | Bid notifications |
| Storage | Cloudflare R2 | Property photos/docs |

---

## 📞 NEXT STEPS FOR YOU

1. ✅ Send me your Stripe publishable key (public key — safe to share)
2. ✅ Confirm domain access — who is your registrar? (GoDaddy, Namecheap, etc.)
3. ✅ Share the logo you mentioned (paste it in chat)
4. ✅ Confirm: is "2,500 notes" = 2,500 property listings you want loaded at launch?
