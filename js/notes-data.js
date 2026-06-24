// Pacific Rim Auction — Notes Marketplace Data & Rendering

const notesData = [
  {
    id: 'N001', type: 'Performing',
    collateral: 'Single Family Residence',
    location: 'Haleiwa, Hawaii, USA', flag: '🇺🇸',
    faceValue: 485000, upb: 412000, interestRate: 6.75, term: 30,
    remainingTerm: 22, ltv: 68, paymentStatus: 'Current — 84 months',
    currentBid: 360000, openTime: 'Hawaii', market: 'North America',
    endTime: Date.now() + (1 * 24 * 60 * 60 * 1000) + (3 * 60 * 60 * 1000),
    noteClass: 'First Lien', color: '#16a34a',
  },
  {
    id: 'N002', type: 'Non-Performing',
    collateral: 'Commercial Office Building',
    location: 'Sydney, New South Wales, Australia', flag: '🇦🇺',
    faceValue: 1850000, upb: 1620000, interestRate: 7.25, term: 25,
    remainingTerm: 18, ltv: 72, paymentStatus: 'Default — 9 months',
    currentBid: 890000, openTime: 'Asia-Pacific', market: 'Asia-Pacific',
    endTime: Date.now() + (2 * 24 * 60 * 60 * 1000),
    noteClass: 'First Lien', color: '#dc2626',
  },
  {
    id: 'N003', type: 'Seller-Financed',
    collateral: 'Beachfront Condo',
    location: 'Cancún, Quintana Roo, Mexico', flag: '🇲🇽',
    faceValue: 320000, upb: 295000, interestRate: 8.0, term: 20,
    remainingTerm: 17, ltv: 75, paymentStatus: 'Current — 36 months',
    currentBid: 245000, openTime: 'US East', market: 'Latin America',
    endTime: Date.now() + (3 * 24 * 60 * 60 * 1000) + (5 * 60 * 60 * 1000),
    noteClass: 'First Lien', color: '#16a34a',
  },
  {
    id: 'N004', type: 'Performing',
    collateral: 'Luxury Condominium',
    location: 'Singapore City, Singapore', flag: '🇸🇬',
    faceValue: 2200000, upb: 1950000, interestRate: 5.5, term: 30,
    remainingTerm: 26, ltv: 65, paymentStatus: 'Current — 48 months',
    currentBid: 1720000, openTime: 'Asia-Pacific', market: 'Asia-Pacific',
    endTime: Date.now() + (4 * 24 * 60 * 60 * 1000),
    noteClass: 'First Lien', color: '#16a34a',
  },
  {
    id: 'N005', type: 'Non-Performing',
    collateral: 'Mixed-Use Development',
    location: 'Vancouver, British Columbia, Canada', flag: '🇨🇦',
    faceValue: 3400000, upb: 3100000, interestRate: 6.9, term: 25,
    remainingTerm: 20, ltv: 78, paymentStatus: 'Default — 6 months',
    currentBid: 1650000, openTime: 'US West', market: 'North America',
    endTime: Date.now() + (1 * 24 * 60 * 60 * 1000) + (8 * 60 * 60 * 1000),
    noteClass: 'First Lien', color: '#dc2626',
  },
  {
    id: 'N006', type: 'Performing',
    collateral: 'Villa with Pool',
    location: 'Bali, Bali Province, Indonesia', flag: '🇮🇩',
    faceValue: 650000, upb: 580000, interestRate: 7.5, term: 20,
    remainingTerm: 16, ltv: 70, paymentStatus: 'Current — 48 months',
    currentBid: 490000, openTime: 'Asia-Pacific', market: 'Asia-Pacific',
    endTime: Date.now() + (5 * 24 * 60 * 60 * 1000),
    noteClass: 'Second Lien', color: '#16a34a',
  },
  {
    id: 'N007', type: 'Seller-Financed',
    collateral: 'Agricultural Land',
    location: 'Oahu, Hawaii, USA', flag: '🇺🇸',
    faceValue: 1100000, upb: 980000, interestRate: 6.25, term: 15,
    remainingTerm: 11, ltv: 60, paymentStatus: 'Current — 48 months',
    currentBid: 860000, openTime: 'Hawaii', market: 'North America',
    endTime: Date.now() + (2 * 24 * 60 * 60 * 1000) + (2 * 60 * 60 * 1000),
    noteClass: 'First Lien', color: '#16a34a',
  },
  {
    id: 'N008', type: 'Non-Performing',
    collateral: 'Retail Strip Mall',
    location: 'Osaka, Osaka Prefecture, Japan', flag: '🇯🇵',
    faceValue: 4200000, upb: 3900000, interestRate: 4.8, term: 30,
    remainingTerm: 24, ltv: 82, paymentStatus: 'Default — 12 months',
    currentBid: 2100000, openTime: 'Asia-Pacific', market: 'Asia-Pacific',
    endTime: Date.now() + (3 * 24 * 60 * 60 * 1000) + (12 * 60 * 60 * 1000),
    noteClass: 'First Lien', color: '#dc2626',
  },
  {
    id: 'N009', type: 'Performing',
    collateral: 'Townhouse',
    location: 'Auckland, New Zealand', flag: '🇳🇿',
    faceValue: 780000, upb: 710000, interestRate: 6.1, term: 25,
    remainingTerm: 21, ltv: 73, paymentStatus: 'Current — 48 months',
    currentBid: 605000, openTime: 'Asia-Pacific', market: 'Asia-Pacific',
    endTime: Date.now() + (6 * 24 * 60 * 60 * 1000),
    noteClass: 'First Lien', color: '#16a34a',
  },
  {
    id: 'N010', type: 'Seller-Financed',
    collateral: 'Ocean View Estate',
    location: 'Marbella, Andalucía, Spain', flag: '🇪🇸',
    faceValue: 2800000, upb: 2500000, interestRate: 5.75, term: 20,
    remainingTerm: 16, ltv: 67, paymentStatus: 'Current — 48 months',
    currentBid: 2100000, openTime: 'London', market: 'Europe',
    endTime: Date.now() + (4 * 24 * 60 * 60 * 1000) + (6 * 60 * 60 * 1000),
    noteClass: 'First Lien', color: '#16a34a',
  },
  {
    id: 'N011', type: 'Non-Performing',
    collateral: 'Hospitality Resort',
    location: 'Phuket, Thailand', flag: '🇹🇭',
    faceValue: 5600000, upb: 5100000, interestRate: 7.0, term: 25,
    remainingTerm: 20, ltv: 76, paymentStatus: 'Default — 15 months',
    currentBid: 2750000, openTime: 'Asia-Pacific', market: 'Asia-Pacific',
    endTime: Date.now() + (2 * 24 * 60 * 60 * 1000) + (10 * 60 * 60 * 1000),
    noteClass: 'First Lien', color: '#dc2626',
  },
  {
    id: 'N012', type: 'Performing',
    collateral: 'High-Rise Unit',
    location: 'Seoul, South Korea', flag: '🇰🇷',
    faceValue: 920000, upb: 845000, interestRate: 5.9, term: 30,
    remainingTerm: 26, ltv: 69, paymentStatus: 'Current — 48 months',
    currentBid: 720000, openTime: 'Asia-Pacific', market: 'Asia-Pacific',
    endTime: Date.now() + (7 * 24 * 60 * 60 * 1000),
    noteClass: 'First Lien', color: '#16a34a',
  }
];

function getDiscount(note) {
  return (((note.upb - note.currentBid) / note.upb) * 100).toFixed(1);
}

function getYield(note) {
  // Simplified yield calc: interest rate × UPB / current bid
  return ((note.interestRate / 100 * note.upb) / note.currentBid * 100).toFixed(1);
}

function renderNoteCard(note) {
  const discount = getDiscount(note);
  const yld = getYield(note);
  const typeColors = {
    'Performing': '#16a34a',
    'Non-Performing': '#dc2626',
    'Seller-Financed': '#0a3d6b',
  };
  const typeBg = {
    'Performing': '#f0fdf4',
    'Non-Performing': '#fef2f2',
    'Seller-Financed': '#eff6ff',
  };

  return `
  <div class="listing-card" data-note-id="${note.id}">
    <div style="background:${typeBg[note.type] || '#f3f4f6'};padding:16px 20px;border-bottom:1px solid #e5e7eb;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        <span style="background:${typeColors[note.type]};color:#fff;font-size:.72rem;font-weight:700;padding:3px 10px;border-radius:999px;text-transform:uppercase;letter-spacing:.05em;">${note.type}</span>
        <span style="font-size:.8rem;font-weight:700;color:${typeColors[note.type]};">−${discount}% Discount</span>
      </div>
      <div style="font-size:.75rem;color:#6b7280;text-transform:uppercase;letter-spacing:.06em;">${note.flag} ${note.location}</div>
      <div style="font-family:var(--font-serif);font-size:1.05rem;font-weight:600;color:#111827;margin-top:4px;">${note.collateral}</div>
    </div>
    <div style="padding:16px 20px;">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px;font-size:.82rem;">
        <div><div style="color:#9ca3af;text-transform:uppercase;font-size:.7rem;letter-spacing:.06em;">Face Value</div><div style="font-weight:700;color:#111827;">${formatCurrency(note.faceValue)}</div></div>
        <div><div style="color:#9ca3af;text-transform:uppercase;font-size:.7rem;letter-spacing:.06em;">UPB</div><div style="font-weight:700;color:#111827;">${formatCurrency(note.upb)}</div></div>
        <div><div style="color:#9ca3af;text-transform:uppercase;font-size:.7rem;letter-spacing:.06em;">Rate / Term</div><div style="font-weight:700;color:#111827;">${note.interestRate}% / ${note.remainingTerm}yr left</div></div>
        <div><div style="color:#9ca3af;text-transform:uppercase;font-size:.7rem;letter-spacing:.06em;">LTV</div><div style="font-weight:700;color:#111827;">${note.ltv}% • ${note.noteClass}</div></div>
      </div>
      <div style="background:#f9fafb;border-radius:8px;padding:12px 16px;margin-bottom:16px;font-size:.82rem;">
        <div style="color:#6b7280;">Payment Status:</div>
        <div style="font-weight:600;color:${note.type === 'Non-Performing' ? '#dc2626' : '#16a34a'};">${note.paymentStatus}</div>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:flex-end;padding-top:12px;border-top:1px solid #e5e7eb;">
        <div>
          <div style="font-size:.72rem;color:#9ca3af;text-transform:uppercase;">Current Bid</div>
          <div style="font-family:var(--font-serif);font-size:1.3rem;font-weight:700;color:var(--ocean);">${formatCurrency(note.currentBid)}</div>
          <div style="font-size:.75rem;color:#16a34a;font-weight:600;">≈${yld}% yield</div>
        </div>
        <div style="text-align:right;">
          <div style="font-size:.7rem;color:#9ca3af;">Closes In</div>
          <div style="font-size:.9rem;font-weight:700;color:#dc2626;font-variant-numeric:tabular-nums;" data-end="${note.endTime}">${formatCountdown(note.endTime)}</div>
          <div style="font-size:.7rem;color:#9ca3af;">Opens: ${note.openTime}</div>
        </div>
      </div>
      <div style="display:flex;gap:8px;margin-top:14px;">
        <a href="note-detail.html?id=${note.id}" class="btn btn-primary" style="flex:1;text-align:center;font-size:.82rem;padding:8px 12px;">View Details</a>
        <a href="register.html" class="btn btn-outline" style="flex:1;text-align:center;font-size:.82rem;padding:8px 12px;">Bid</a>
      </div>
    </div>
  </div>
  `;
}

function initNotesGrid() {
  const grid = document.getElementById('notesGrid');
  if (!grid) return;
  grid.innerHTML = notesData.map(renderNoteCard).join('');
}

document.addEventListener('DOMContentLoaded', initNotesGrid);
