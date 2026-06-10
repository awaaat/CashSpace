import React from 'react';
import styles from './Topbar.module.css';

export default function Topbar({
  user,
  notifications,
  unreadCount,
  onNavigate,
  onLogout,
  settingsDropOpen,
  setSettingsDropOpen,
  settingsDropRef,
  showNotifications,
  setShowNotifications,
  notifPanelRef,
  loadNotifications,
  notifPage,
  notifHasMore,
  notifLoading,
  markNotifRead,
  markAllNotifsRead
}) {
  return (
    <header className={styles.topbar}>
      <div className={styles.actions}>

        {/* Notifications — ref wraps bell + panel so outside clicks close it */}
        <div className={styles.notifWrapper} ref={notifPanelRef}>
          <button
            className={styles.iconBtn}
            onClick={() => setShowNotifications(!showNotifications)}
          >
            🔔
            {unreadCount > 0 && <span className={styles.badge}>{unreadCount}</span>}
          </button>

          {showNotifications && (
            <div className={styles.notifPanel}>
              <div className={styles.notifHeader}>
                <span>Notifications</span>
                {unreadCount > 0 && (
                  <button className={styles.markAllBtn} onClick={markAllNotifsRead}>
                    Mark all read
                  </button>
                )}
              </div>
              <div className={styles.notifList}>
                {notifLoading && notifications.length === 0 && (
                  <div className={styles.loadingSmall}>Loading…</div>
                )}
                {notifications.length === 0 && !notifLoading && (
                  <div className={styles.empty}>No notifications</div>
                )}
                {notifications.map(n => (
                  <div
                    key={n.id}
                    className={`${styles.notifItem} ${!n.is_read ? styles.unread : ''}`}
                    onClick={() => !n.is_read && markNotifRead(n.id)}
                  >
                    <div className={styles.notifTitle}>{n.title}</div>
                    <div className={styles.notifMessage}>{n.message}</div>
                    <div className={styles.notifDate}>
                      {new Date(n.created_at).toLocaleDateString()}
                    </div>
                  </div>
                ))}
                {notifHasMore && (
                  <button
                    className={styles.loadMoreBtn}
                    onClick={() => loadNotifications(notifPage + 1, false)}
                  >
                    Load more
                  </button>
                )}
              </div>
            </div>
          )}
        </div>

        {/* User menu */}
        <div className={styles.settingsWrapper} ref={settingsDropRef}>
          <button
            className={styles.avatar}
            onClick={() => setSettingsDropOpen(!settingsDropOpen)}
          >
            {(user?.first_name || user?.email || '?')[0].toUpperCase()}
          </button>
          {settingsDropOpen && (
            <div className={styles.dropdown}>
              <div className={styles.dropdownHeader}>
                <div>{user?.full_name || user?.email}</div>
                <div className={styles.dropdownRole}>{user?.role}</div>
              </div>
              <button onClick={() => { onNavigate('/settings'); setSettingsDropOpen(false); }}>
                Settings
              </button>
              <button onClick={() => { onLogout(); setSettingsDropOpen(false); }}>
                Sign out
              </button>
            </div>
          )}
        </div>

      </div>
    </header>
  );
}