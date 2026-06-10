import React from 'react';
import styles from './RoleCards.module.css';

const Card = ({ icon, title, description, bullets, buttonText, buttonAction, isActive = true }) => (
  <div className={`${styles.card} ${!isActive ? styles.inactive : ''}`}>
    <div className={styles.icon}>{icon}</div>
    <h3 className={styles.title}>{title}</h3>
    <p className={styles.description}>{description}</p>
    <ul className={styles.bullets}>
      {bullets.map((b, i) => <li key={i}>{b}</li>)}
    </ul>
    <button onClick={buttonAction} className={styles.button}>
      {buttonText} →
    </button>
  </div>
);

export default function RoleCards({ hasMerchant, hasCreator, onNavigate }) {
  return (
    <div className={styles.container}>
      <Card
        icon=""
        title="Buy Crypto"
        description="Purchase Bitcoin, Ethereum, USDT, or USDC using your credit/debit card. Your crypto is sent directly to your chosen wallet – no hidden fees, no account freezes."
        bullets={[
          "Instant settlement (≈2 min)",
          "Non‑custodial – you own your keys",
          "No minimum purchase (except network fees)"
        ]}
        buttonText="Buy crypto now"
        buttonAction={() => onNavigate('/buy')}
      />
      <Card
        icon=""
        title="Merchant"
        description="Sell digital products, subscriptions, or community access. Automate delivery via Telegram, Discord, email, or webhook. No merchant account rejection – we welcome high‑risk businesses."
        bullets={[
          "No monthly fees – pay per transaction",
          "Your customers pay in local fiat (card, M‑Pesa, etc.)",
          "You receive crypto settlement automatically"
        ]}
        buttonText={hasMerchant ? "Go to merchant dashboard" : "Apply to become a merchant"}
        buttonAction={() => onNavigate(hasMerchant ? '/merchant' : '/merchant/register')}
      />
      <Card
        icon=""
        title="Creator"
        description="Turn any link, file, or hidden content into a pay‑to‑unlock resource. Share a simple checkout page – customers pay, you get paid, and they receive access."
        bullets={[
          "Zero setup – just paste a link or upload a file",
          "Works with any audience, anywhere",
          "Automated access links – no manual work"
        ]}
        buttonText={hasCreator ? "Go to creator dashboard" : "Activate creator account"}
        buttonAction={() => onNavigate(hasCreator ? '/creator' : '/creator/register')}
      />
    </div>
  );
}