// frontend/src/pages/Creator/CreateAsset.jsx
import React, { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import { creatorApi } from "../../api/creator";
import { authApi } from "../../api/auth";
import { shortDate } from "../../utils/formatters";
import styles from "./CreatorDashboard.module.css"; // Reuse the same styles

// Toast component (same as dashboard)
function Toast({ message, type, onClose }) {
  useEffect(() => {
    const timer = setTimeout(onClose, 4000);
    return () => clearTimeout(timer);
  }, [onClose]);
  return (
    <div className={`${styles.toast} ${styles[`toast_${type}`]}`}>
      <span>{message}</span>
      <button onClick={onClose}>×</button>
    </div>
  );
}

// Confirm modal (same as dashboard)
function ConfirmModal({ isOpen, title, message, onConfirm, onCancel }) {
  if (!isOpen) return null;
  return (
    <div className={styles.modalOverlay} onClick={onCancel}>
      <div className={styles.confirmModal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.confirmHeader}>
          <h3>{title || "Confirm"}</h3>
          <button className={styles.confirmClose} onClick={onCancel}>×</button>
        </div>
        <div className={styles.confirmBody}>{message}</div>
        <div className={styles.confirmFooter}>
          <button className={styles.confirmCancel} onClick={onCancel}>Cancel</button>
          <button className={styles.confirmOk} onClick={onConfirm}>Confirm</button>
        </div>
      </div>
    </div>
  );
}

export default function CreateAsset() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [settingsDropOpen, setSettingsDropOpen] = useState(false);
  const settingsDropRef = useRef(null);
  const [toasts, setToasts] = useState([]);
  const toastId = useRef(0);
  const [loading, setLoading] = useState(false);

  // Notifications state
  const [notifications, setNotifications] = useState([]);
  const [notifLoading, setNotifLoading] = useState(false);
  const [unreadNotifCount, setUnreadNotifCount] = useState(0);
  const [notifPage, setNotifPage] = useState(1);
  const [notifHasMore, setNotifHasMore] = useState(true);
  const notifLoaded = useRef(false);
  const [showNotifications, setShowNotifications] = useState(false);

  // Form state
  const [form, setForm] = useState({
    title: "",
    description: "",
    asset_type: "url",
    unlock_value: "",
    pricing_type: "fixed",
    price_usd: "",
    min_price_usd: "5",
    is_active: true,
  });

  const showToast = useCallback((msg, type = "success") => {
    const id = ++toastId.current;
    setToasts(prev => [...prev, { id, message: msg, type }]);
  }, []);
  const hideToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  // Load notifications (same as dashboard)
  const loadNotifications = async (page = 1, reset = true) => {
    if (notifLoading) return;
    setNotifLoading(true);
    try {
      const res = await authApi.getNotifications({ page, page_size: 20 });
      const results = res.data.results || [];
      if (reset) {
        setNotifications(results);
        setNotifPage(page);
        setNotifHasMore(!!res.data.next);
      } else {
        setNotifications(prev => [...prev, ...results]);
        setNotifPage(page);
        setNotifHasMore(!!res.data.next);
      }
    } catch {
      showToast("Failed to load notifications", "error");
    } finally {
      setNotifLoading(false);
    }
  };

  const loadUnreadCount = async () => {
    try {
      const res = await authApi.getUnreadNotificationCount();
      setUnreadNotifCount(res.data.unread_count);
    } catch {}
  };

  const markNotifRead = async (id) => {
    try {
      await authApi.markNotificationRead(id);
      setNotifications(prev => prev.map(n => n.id === id ? { ...n, is_read: true } : n));
      setUnreadNotifCount(prev => Math.max(0, prev - 1));
    } catch {
      showToast("Failed to mark as read", "error");
    }
  };

  const markAllNotifsRead = async () => {
    try {
      await authApi.markAllNotificationsRead();
      setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
      setUnreadNotifCount(0);
      showToast("All notifications marked as read", "success");
    } catch {
      showToast("Failed to mark all as read", "error");
    }
  };

  useEffect(() => {
    if (!notifLoaded.current) {
      notifLoaded.current = true;
      loadNotifications(1, true);
      loadUnreadCount();
    }
  }, []);

  useEffect(() => {
    const handler = (e) => {
      if (settingsDropRef.current && !settingsDropRef.current.contains(e.target)) {
        setSettingsDropOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setForm(prev => ({
      ...prev,
      [name]: type === "checkbox" ? checked : value,
    }));
  };

  const validateForm = () => {
    if (!form.title.trim()) {
      showToast("Title is required", "error");
      return false;
    }
    if (!form.unlock_value.trim()) {
      showToast("Unlock value is required", "error");
      return false;
    }
    if (form.asset_type === "url") {
      try {
        new URL(form.unlock_value);
      } catch {
        showToast("Please enter a valid URL", "error");
        return false;
      }
    }
    if (form.pricing_type === "fixed") {
      const price = parseFloat(form.price_usd);
      if (isNaN(price) || price < 0.01) {
        showToast("Price must be at least $0.01", "error");
        return false;
      }
    }
    if (form.pricing_type === "pwyw") {
      const min = parseFloat(form.min_price_usd);
      if (isNaN(min) || min < 0.01) {
        showToast("Minimum price must be at least $0.01", "error");
        return false;
      }
    }
    return true;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!validateForm()) return;
    setLoading(true);
    try {
      const payload = {
        title: form.title,
        description: form.description,
        asset_type: form.asset_type,
        unlock_value: form.unlock_value,
        pricing_type: form.pricing_type,
        is_active: form.is_active,
      };
      if (form.pricing_type === "fixed") {
        payload.price_usd = parseFloat(form.price_usd);
      } else {
        payload.min_price_usd = parseFloat(form.min_price_usd);
      }
      await creatorApi.createAsset(payload);
      showToast("Payable link created", "success");
      setTimeout(() => navigate("/creator"), 1500);
    } catch (err) {
      const msg = err.response?.data?.detail || "Failed to create asset";
      showToast(msg, "error");
    } finally {
      setLoading(false);
    }
  };

  const navItems = [
    { id: "overview", label: "Overview" },
    { id: "assets", label: "My Links" },
    { id: "sales", label: "Sales" },
    { id: "affiliate", label: "Affiliate" },
    { id: "discounts", label: "Discounts" },
    { id: "settings", label: "Settings" },
  ];

  return (
    <div className={styles.root}>
      {/* Sidebar */}
      <aside className={`${styles.sidebar} ${sidebarOpen ? styles.sidebarOpen : ""}`}>
        <div className={styles.sidebarHead}>
          <Link to="/" className={styles.logo}>
            <span className={styles.logoMark}>C</span>
            <span className={styles.logoText}>Creator</span>
          </Link>
          <button className={styles.sidebarClose} onClick={() => setSidebarOpen(false)}>✕</button>
        </div>
        <nav className={styles.nav}>
          <div className={styles.navGroup}>
            {navItems.map(item => (
              <button
                key={item.id}
                className={styles.navItem}
                onClick={() => navigate(item.id === "overview" ? "/creator" : `/creator/${item.id}`)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </nav>
        <div className={styles.sidebarFoot}>
          <div className={styles.userChip}>
            <div className={styles.userAvatar}>
              {(user?.first_name || user?.email || "?")[0].toUpperCase()}
            </div>
            <div className={styles.userInfo}>
              <span className={styles.userName}>{user?.full_name || user?.email}</span>
              <span className={styles.userRole}>Creator</span>
            </div>
          </div>
          <button className={styles.logoutBtn} onClick={() => logout().then(() => navigate("/login"))}>
            Sign out
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className={styles.main}>
        <header className={styles.topbar}>
          <button className={styles.menuBtn} onClick={() => setSidebarOpen(true)}>☰</button>
          <div className={styles.topbarLeft}>
            <h2 className={styles.pageTitle}>Create payable link</h2>
          </div>
          <div className={styles.topbarRight}>
            <div className={styles.notifWrapper}>
              <button
                className={styles.topbarIcon}
                onClick={() => setShowNotifications(!showNotifications)}
              >
                🔔 {unreadNotifCount > 0 && <span className={styles.topBadge}>{unreadNotifCount}</span>}
              </button>
              {showNotifications && (
                <div className={styles.notifDropdown}>
                  <div className={styles.notifHeader}>
                    <span>Notifications</span>
                    {unreadNotifCount > 0 && (
                      <button onClick={markAllNotifsRead} className={styles.markAllBtn}>Mark all read</button>
                    )}
                  </div>
                  <div className={styles.notifList}>
                    {notifLoading && notifications.length === 0 && <div className={styles.loadingSmall}>Loading…</div>}
                    {notifications.length === 0 && !notifLoading && <div className={styles.emptyNotif}>No notifications</div>}
                    {notifications.map(n => (
                      <div
                        key={n.id}
                        className={`${styles.notifItem} ${!n.is_read ? styles.unread : ""}`}
                        onClick={() => !n.is_read && markNotifRead(n.id)}
                      >
                        <div className={styles.notifTitle}>{n.title}</div>
                        <div className={styles.notifMessage}>{n.message}</div>
                        <div className={styles.notifDate}>{shortDate(n.created_at)}</div>
                      </div>
                    ))}
                    {notifHasMore && (
                      <button onClick={() => loadNotifications(notifPage + 1, false)} className={styles.loadMoreBtn}>
                        Load more
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
            <div ref={settingsDropRef} style={{ position: "relative" }}>
              <button
                className={styles.topAvatar}
                onClick={() => setSettingsDropOpen(o => !o)}
                title="Account settings"
              >
                {(user?.first_name || user?.email || "?")[0].toUpperCase()}
              </button>
              {settingsDropOpen && (
                <div className={styles.dropdown}>
                  <div className={styles.dropdownHeader}>
                    <div>{user?.full_name || user?.email}</div>
                    <div className={styles.dropdownRole}>Creator</div>
                  </div>
                  <button onClick={() => navigate("/creator/settings")}>Settings</button>
                  <button onClick={() => logout().then(() => navigate("/login"))}>Sign out</button>
                </div>
              )}
            </div>
          </div>
        </header>

        <div className={styles.content}>
          <div className={styles.createFormContainer}>
            <div className={styles.card}>
              <form onSubmit={handleSubmit} className={styles.form}>
                <div className={styles.field}>
                  <label>Title *</label>
                  <input
                    type="text"
                    name="title"
                    value={form.title}
                    onChange={handleChange}
                    placeholder="e.g., Premium Tutorial Video"
                    required
                  />
                </div>
                <div className={styles.field}>
                  <label>Description (optional)</label>
                  <textarea
                    name="description"
                    value={form.description}
                    onChange={handleChange}
                    placeholder="Describe what the buyer gets"
                    rows="3"
                  />
                </div>
                <div className={styles.fieldGroup}>
                  <div className={styles.field}>
                    <label>Asset type</label>
                    <select name="asset_type" value={form.asset_type} onChange={handleChange}>
                      <option value="url">External URL (video, course, private page)</option>
                      <option value="file">File download (PDF, ZIP, MP4)</option>
                      <option value="content">Hidden text / HTML</option>
                      <option value="api_key">API key / License key</option>
                    </select>
                  </div>
                  <div className={styles.field}>
                    <label>Pricing type</label>
                    <select name="pricing_type" value={form.pricing_type} onChange={handleChange}>
                      <option value="fixed">Fixed price</option>
                      <option value="pwyw">Pay what you want</option>
                    </select>
                  </div>
                </div>
                <div className={styles.field}>
                  <label>Unlock value *</label>
                  {form.asset_type === "url" ? (
                    <input
                      type="url"
                      name="unlock_value"
                      value={form.unlock_value}
                      onChange={handleChange}
                      placeholder="https://example.com/secret-content"
                      required
                    />
                  ) : (
                    <textarea
                      name="unlock_value"
                      value={form.unlock_value}
                      onChange={handleChange}
                      placeholder="The content that becomes visible after payment"
                      rows="4"
                      required
                    />
                  )}
                </div>
                {form.pricing_type === "fixed" ? (
                  <div className={styles.field}>
                    <label>Price (USD) *</label>
                    <input
                      type="number"
                      name="price_usd"
                      value={form.price_usd}
                      onChange={handleChange}
                      step="0.01"
                      min="0.01"
                      placeholder="9.99"
                      required
                    />
                  </div>
                ) : (
                  <div className={styles.field}>
                    <label>Minimum price (USD)</label>
                    <input
                      type="number"
                      name="min_price_usd"
                      value={form.min_price_usd}
                      onChange={handleChange}
                      step="0.01"
                      min="0.01"
                      placeholder="5.00"
                    />
                    <span className={styles.hint}>Buyers can pay more than this amount.</span>
                  </div>
                )}
                <div className={styles.checkboxField}>
                  <input
                    type="checkbox"
                    name="is_active"
                    checked={form.is_active}
                    onChange={handleChange}
                  />
                  <label>Active (visible to buyers)</label>
                </div>
                <div className={styles.actions}>
                  <button type="button" onClick={() => navigate("/creator")} className={styles.secondaryButton}>
                    Cancel
                  </button>
                  <button type="submit" className={styles.primaryButton} disabled={loading}>
                    {loading ? "Creating..." : "Create payable link"}
                  </button>
                </div>
              </form>
              <div className={styles.info}>
                <p>How it works:</p>
                <ul>
                  <li>Buyers see a simple checkout page with your price.</li>
                  <li>After payment, they receive a unique access link.</li>
                  <li>CashSpace takes a small commission (default 30%).</li>
                  <li>You receive payouts to your wallet.</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </main>

      {sidebarOpen && <div className={styles.overlay} onClick={() => setSidebarOpen(false)} />}
      <div className={styles.toastStack}>
        {toasts.map(t => <Toast key={t.id} message={t.message} type={t.type} onClose={() => hideToast(t.id)} />)}
      </div>
    </div>
  );
}