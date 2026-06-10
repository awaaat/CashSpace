import React from 'react';
import styles from './WelcomeBanner.module.css';

export default function WelcomeBanner({ userName, hasWallets, onAddWallet }) {
  return (
    <div className={styles.wrapper}>
      <h2 className={styles.title}>Welcome back, {userName}</h2>
      <p className={styles.subtitle}>
        CashSpace lets you <strong>receive payments</strong> from customers worldwide,
        and <strong>buy crypto</strong> with your card. All in one dashboard.
      </p>

      {!hasWallets && (
        <div className={styles.alert}>
          <span>You haven't added a payout wallet yet.</span>
          <button onClick={onAddWallet} className={styles.alertBtn}>
            Add wallet →
          </button>
        </div>
      )}

      <div className={styles.eduTip}>
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-start' }}>
          <div>
            <p className={styles.highlight} style={{ fontWeight: 600, marginBottom: '0.25rem' }}>
              New to CashSpace?
            </p>
            <ul>
              <li><strong>Buy Crypto</strong> – purchase Bitcoin, Ethereum, USDT with your card.</li>
              <li><strong>Merchant</strong> – sell digital products, subscriptions, get paid in crypto.</li>
              <li><strong>Creator</strong> – turn any link into a pay‑to‑unlock resource.</li>
            </ul>
            <p className={styles.highlight} style={{ marginTop: '0.5rem' }}>
              Start with buying crypto or explore the tabs below.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}