import React, { useState } from 'react';
import styles from './Sidebar.module.css';

export default function Sidebar({ user, hasMerchant, hasCreator, onNavigate, onLogout }) {
  const [mobileOpen, setMobileOpen] = useState(false);

  const navItems = [
    { path: '/dashboard', label: 'Dashboard' },
    { path: '/buy', label: 'Buy Crypto' },
    { path: '/history', label: 'History' },
    { path: '/Profile', label: 'Profile' },
  ];
  if (hasMerchant) navItems.push({ path: '/merchant', label: 'Merchant Dashboard' });
  else navItems.push({ path: '/merchant/register', label: 'Become Merchant →' });
  if (hasCreator) navItems.push({ path: '/creator', label: 'Creator' });
  else navItems.push({ path: '/creator/register', label: 'Creator Dashboard' });

  return (
    <>
      <aside className={`${styles.sidebar} ${mobileOpen ? styles.open : ''}`}>
        <div className={styles.head}>
          <a href="/" className={styles.logo}>
            <div className={styles.logoMark}>C</div>
            <span className={styles.logoText}>CashSpace</span>
          </a>
          {/* Close button removed as requested */}
        </div>
        <nav className={styles.nav}>
          {navItems.map(item => (
            <button
              key={item.path}
              onClick={() => onNavigate(item.path)}
              className={styles.navItem}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <div className={styles.footer}>
          <div className={styles.userChip}>
            <div className={styles.avatar}>
              {(user?.first_name || user?.email || '?')[0].toUpperCase()}
            </div>
            <div>
              <div className={styles.userName}>{user?.full_name || user?.email}</div>
              <div className={styles.userRole}>{user?.role}</div>
            </div>
          </div>
          <button onClick={onLogout} className={styles.logoutBtn}>Sign out</button>
        </div>
      </aside>

      <button className={styles.menuBtn} onClick={() => setMobileOpen(true)}>☰</button>
      {mobileOpen && <div className={styles.overlay} onClick={() => setMobileOpen(false)} />}
    </>
  );
}