import React from 'react';
import { formatUSD, shortDate, truncateWallet, statusColor } from '../../utils/formatters';
import styles from './RecentTransactions.module.css';

export default function RecentTransactions({ payments, loading, onViewAll, onBuy }) {
  if (loading) {
    return <div className={styles.loadingRows} />;
  }
  if (payments.length === 0) {
    return (
      <div className={styles.empty}>
        <p>No transactions yet.</p>
        <button onClick={onBuy} className={styles.emptyBtn}>Buy crypto →</button>
      </div>
    );
  }
  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h3>Recent transactions</h3>
        <button onClick={onViewAll} className={styles.link}>View all →</button>
      </div>
      <div>
        {payments.map(p => (
          <div key={p.id} className={styles.row}>
            <div className={styles.left}>
              <div
                className={styles.icon}
                style={{ background: `${statusColor(p.status)}20`, color: statusColor(p.status) }}
              >
                {p.currency_code === 'BTC' ? '₿' : p.currency_code === 'ETH' ? 'Ξ' : '💳'}
              </div>
              <div>
                <div className={styles.title}>{p.currency_code} purchase</div>
                <div className={styles.sub}>
                  {shortDate(p.created_at)} · {truncateWallet(p.destination_wallet)}
                </div>
              </div>
            </div>
            <div className={styles.right}>
              <div className={styles.amount}>{formatUSD(p.amount_usd)}</div>
              <div className={styles.status} style={{ color: statusColor(p.status) }}>
                {p.status}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}