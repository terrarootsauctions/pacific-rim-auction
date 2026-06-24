// Netlify Serverless Function: create-checkout-session
// File: netlify/functions/create-checkout-session.js
// Deploy this alongside your site on Netlify

const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);

exports.handler = async (event) => {
  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, body: 'Method Not Allowed' };
  }

  try {
    const payload = JSON.parse(event.body);
    const { package: pkg, price, property, seller } = payload;

    const packageNames = {
      standard: 'Standard Listing Package',
      premium:  'Premium Listing Package',
      luxury:   'Luxury White-Glove Listing Package',
    };

    const session = await stripe.checkout.sessions.create({
      payment_method_types: ['card'],
      mode: 'payment',
      customer_email: seller.email,
      line_items: [{
        price_data: {
          currency: 'usd',
          unit_amount: price * 100, // cents
          product_data: {
            name: packageNames[pkg] || 'Listing Package',
            description: `Pacific Rim Auction listing for: ${property.address}`,
          },
        },
        quantity: 1,
      }],
      metadata: {
        package: pkg,
        property_address: property.address,
        property_type: property.type,
        start_bid: property.startBid,
        seller_name: `${seller.firstName} ${seller.lastName}`,
        seller_phone: seller.phone,
      },
      success_url: `${process.env.SITE_URL}/listing-success.html?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url:  `${process.env.SITE_URL}/list-property.html`,
    });

    return {
      statusCode: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: session.url }),
    };
  } catch (err) {
    console.error('Stripe error:', err);
    return {
      statusCode: 500,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ error: err.message }),
    };
  }
};
