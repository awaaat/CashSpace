import React from 'react';
import { formatUSD } from '../../utils/formatters';
import styles from './StatsCards.module.css';

export default function StatsCards({ totalSpent, merchantStats, creatorStats, hasMerchant, hasCreator }) {
  const stats = [
    { icon: '', label: 'Total spent', value: formatUSD(totalSpent), hint: 'Crypto purchases' },
    { icon: '', label: 'Merchant', value: hasMerchant ? (merchantStats?.total_sales || 0) : '—', hint: hasMerchant ? `${formatUSD(merchantStats?.total_revenue_usd || 0)} revenue` : 'Not active yet' },
    { icon: '', label: 'Creator', value: hasCreator ? (creatorStats?.total_sales || 0) : '—', hint: hasCreator ? `${formatUSD(creatorStats?.total_revenue_usd || 0)} earned` : 'Not active yet' },
  ];

  return (
    <div className={styles.container}>
      {stats.map((s, i) => (
        <div key={i} className={styles.card}>
          <div className={styles.header}>
            <span className={styles.icon}>{s.icon}</span>
            <span className={styles.label}>{s.label}</span>
          </div>
          <div className={styles.value}>{s.value}</div>
          <div className={styles.hint}>{s.hint}</div>
        </div>
      ))}
    </div>
  );
}