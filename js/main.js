// Pacific Rim Auction — Main JS

// ---- SAMPLE LISTINGS DATA ----
const listings = [
  {
    id: 1,
    title: "Oceanfront Estate — North Shore",
    location: "Haleiwa, Oahu, Hawaii",
    beds: 4, baths: 3, sqft: 2850,
    currentBid: 1850000,
    endTime: Date.now() + (2 * 24 * 60 * 60 * 1000) + (4 * 60 * 60 * 1000),
    status: "live",
    img: null,
    type: "Single Family"
  },
  {
    id: 2,
    title: "Kauai Beachfront Villa",
    location: "Poipu, Kauai, Hawaii",
    beds: 5, baths: 4, sqft: 3600,
    currentBid: 2950000,
    endTime: Date.now() + (1 * 24 * 60 * 60 * 1000) + (2 * 60 * 60 * 1000),
    status: "ending",
    img: null,
    type: "Luxury Villa"
  },
  {
    id: 3,
    title: "Maui Hillside Retreat",
    location: "Kula, Maui, Hawaii",
    beds: 3, baths: 2, sqft: 1950,
    currentBid: 975000,
    endTime: Date.now() + (3 * 24 * 60 * 60 * 1000) + (6 * 60 * 60 * 1000),
    status: "live",
    img: null,
    type: "Single Family"
  },
  {
    id: 4,
    title: "Malibu Coastal Home",
    location: "Malibu, California, USA",
    beds: 4, baths: 3, sqft: 3100,
    currentBid: 3200000,
    endTime: Date.now() + (5 * 24 * 60 * 60 * 1000),
    status: "live",
    img: null,
    type: "Coastal Home"
  },
  {
    id: 5,
    title: "Sydney Harbour View Penthouse",
    location: "Kirribilli, Sydney, Australia",
    beds: 3, baths: 2, sqft: 2200,
    currentBid: 4100000,
    endTime: Date.now() + (4 * 24 * 60 * 60 * 1000) + (10 * 60 * 60 * 1000),
    status: "live",
    img: null,
    type: "Penthouse"
  },
  {
    id: 6,
    title: "Vancouver Waterfront Condo",
    location: "Coal Harbour, Vancouver, Canada",
    beds: 2, baths: 2, sqft: 1420,
    currentBid: 1150000,
    endTime: Date.now() + (6 * 24 * 60 * 60 * 1000),
    status: "live",
    img: null,
    type: "Condo"
  }
];

function formatCurrency(amount) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(amount);
}

function getTimeLeft(endTime) {
  const diff = endTime - Date.now();
  if (diff <= 0) return { d: 0, h: 0, m: 0, s: 0, expired: true };
  const d = Math.floor(diff / 86400000);
  const h = Math.floor((diff % 86400000) / 3600000);
  const m = Math.floor((diff % 3600000) / 60000);
  const s = Math.floor((diff % 60000) / 1000);
  return { d, h, m, s, expired: false };
}

function formatCountdown(endTime) {
  const t = getTimeLeft(endTime);
  if (t.expired) return 'Closed';
  if (t.d > 0) return `${t.d}d ${t.h}h ${t.m}m`;
  return `${t.h}h ${t.m}m ${t.s}s`;
}

function renderListingCard(listing) {
  const bgColors = [
    'linear-gradient(135deg, #0a3d6b, #1565a0)',
    'linear-gradient(135deg, #1565a0, #2196f3)',
    'linear-gradient(135deg, #0d5a8a, #1a7aad)',
    'linear-gradient(135deg, #1a237e, #283593)',
    'linear-gradient(135deg, #004d40, #00796b)',
    'linear-gradient(135deg, #4a148c, #7b1fa2)',
  ];
  const bg = bgColors[listing.id % bgColors.length];
  const isEnding = listing.status === 'ending';

  return `
    <div class="listing-card" data-id="${listing.id}">
      <div class="listing-img" style="background: ${bg};">
        <div class="listing-status ${isEnding ? 'ending' : ''}">${isEnding ? '⏰ Ending Soon' : '🟢 Live Auction'}</div>
        <div style="position:absolute;bottom:12px;right:12px;background:rgba(0,0,0,.4);color:#fff;padding:4px 10px;border-radius:999px;font-size:.75rem;font-weight:600;">${listing.type}</div>
      </div>
      <div class="listing-body">
        <div class="listing-location">📍 ${listing.location}</div>
        <div class="listing-title">${listing.title}</div>
        <div class="listing-meta">
          <span>🛏 ${listing.beds} beds</span>
          <span>🚿 ${listing.baths} baths</span>
          <span>📐 ${listing.sqft.toLocaleString()} sqft</span>
        </div>
        <div class="listing-bid-row">
          <div class="listing-current-bid">
            <div class="listing-bid-label">Current Bid</div>
            <div class="listing-bid-amount">${formatCurrency(listing.currentBid)}</div>
          </div>
          <div class="listing-countdown">
            <div class="countdown-label">Closes In</div>
            <div class="countdown-time" data-end="${listing.endTime}">${formatCountdown(listing.endTime)}</div>
          </div>
        </div>
        <div class="listing-actions">
          <a href="auction.html?id=${listing.id}" class="btn btn-primary" style="font-size:.85rem;padding:8px 16px;">View Auction</a>
          <a href="register.html" class="btn btn-outline" style="font-size:.85rem;padding:8px 16px;">Register to Bid</a>
        </div>
      </div>
    </div>
  `;
}

// ---- INIT FEATURED LISTINGS ----
function initFeaturedListings() {
  const grid = document.getElementById('featuredListings');
  if (!grid) return;
  grid.innerHTML = listings.slice(0, 6).map(renderListingCard).join('');
}

// ---- INIT ALL LISTINGS ----
function initAllListings() {
  const grid = document.getElementById('allListings');
  if (!grid) return;
  grid.innerHTML = listings.map(renderListingCard).join('');
}

// ---- LIVE COUNTDOWN ----
function updateCountdowns() {
  document.querySelectorAll('.countdown-time[data-end]').forEach(el => {
    const end = parseInt(el.dataset.end, 10);
    el.textContent = formatCountdown(end);
  });
}

// ---- MOBILE MENU ----
function toggleMenu() {
  const menu = document.getElementById('mobileMenu');
  if (menu) menu.classList.toggle('open');
}

// ---- AUCTION DETAIL PAGE ----
function initAuctionDetail() {
  const params = new URLSearchParams(window.location.search);
  const id = parseInt(params.get('id'), 10);
  const listing = listings.find(l => l.id === id);
  if (!listing) return;

  const titleEl = document.getElementById('auctionTitle');
  const locationEl = document.getElementById('auctionLocation');
  const currentBidEl = document.getElementById('currentBidAmount');
  if (titleEl) titleEl.textContent = listing.title;
  if (locationEl) locationEl.textContent = listing.location;
  if (currentBidEl) currentBidEl.textContent = formatCurrency(listing.currentBid);

  // Countdown
  function updateDetail() {
    const t = getTimeLeft(listing.endTime);
    ['days','hours','minutes','seconds'].forEach((unit, i) => {
      const el = document.getElementById(`cd-${unit}`);
      if (el) el.textContent = String([t.d, t.h, t.m, t.s][i]).padStart(2, '0');
    });
  }
  updateDetail();
  setInterval(updateDetail, 1000);

  // Min bid
  const minBid = Math.ceil(listing.currentBid * 1.02 / 1000) * 1000;
  const bidInput = document.getElementById('bidAmount');
  if (bidInput) { bidInput.min = minBid; bidInput.placeholder = formatCurrency(minBid); }
}

// ---- BID SUBMISSION ----
function submitBid(e) {
  e.preventDefault();
  const input = document.getElementById('bidAmount');
  if (!input) return;
  const amount = parseFloat(input.value.replace(/[^0-9.]/g, ''));
  if (!amount || amount <= 0) { alert('Please enter a valid bid amount.'); return; }
  alert(`✅ Bid of ${formatCurrency(amount)} submitted! You will receive confirmation at your registered email.\n\nRemember: Our 7-Day Buyer Confidence Guarantee gives you full due diligence time.`);
}

// ---- INIT ----
document.addEventListener('DOMContentLoaded', () => {
  initFeaturedListings();
  initAllListings();
  initAuctionDetail();
  setInterval(updateCountdowns, 1000);

  const bidForm = document.getElementById('bidForm');
  if (bidForm) bidForm.addEventListener('submit', submitBid);
});
