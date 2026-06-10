// frontend/src/pages/Creator/CreatorDashboard.jsx
import React, { useEffect, useState, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import { creatorApi } from "../../api/creator";
import { authApi } from "../../api/auth";
import {
  formatUSD,
  formatDate,
  truncateWallet,
  shortDate,
  statusColor,
} from "../../utils/formatters";
import styles from "./CreatorDashboard.module.css";

// ── Toast ────────────────────────────────────────────────────────────────
function Toast({ message, type, onClose }) {
  useEffect(() => {
    const t = setTimeout(onClose, 4000);
    return () => clearTimeout(t);
  }, [onClose]);
  return (
    <div className={`${styles.toast} ${styles[`toast_${type}`]}`}>
      <span>{message}</span>
      <button onClick={onClose}>×</button>
    </div>
  );
}

// ── Confirm Modal ───────────────────────────────────────────────────────
function ConfirmModal({ isOpen, title, message, onConfirm, onCancel }) {
  if (!isOpen) return null;
  return (
    <div className={styles.modalOverlay} onClick={onCancel}>
      <div className={styles.confirmModal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.confirmHeader}>
          <h3>{title || "Confirm Action"}</h3>
          <button className={styles.confirmClose} onClick={onCancel}>×</button>
        </div>
        <div className={styles.confirmBody}>
          <p>{message}</p>
        </div>
        <div className={styles.confirmFooter}>
          <button className={styles.confirmCancel} onClick={onCancel}>Cancel</button>
          <button className={styles.confirmOk} onClick={onConfirm}>Confirm</button>
        </div>
      </div>
    </div>
  );
}

// ── Main Component ──────────────────────────────────────────────────────
export default function CreatorDashboard() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  // Data states
  const [profile, setProfile] = useState(null);
  const [assets, setAssets] = useState([]);
  const [sales, setSales] = useState([]);
  const [stats, setStats] = useState(null);
  const [affiliateStats, setAffiliateStats] = useState(null);
  const [discounts, setDiscounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("overview");

  // UI states
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [settingsDropOpen, setSettingsDropOpen] = useState(false);
  const settingsDropRef = useRef(null);
  const [toasts, setToasts] = useState([]);
  const toastId = useRef(0);
  const [confirmState, setConfirmState] = useState({ isOpen: false, action: null, assetId: null, discountId: null });
  const [showDiscountForm, setShowDiscountForm] = useState(false);
  const [newDiscount, setNewDiscount] = useState({ code: "", discount_type: "percent", discount_value: "", max_uses: 1, valid_to: "" });

  // Notifications
  const [notifications, setNotifications] = useState([]);
  const [notifLoading, setNotifLoading] = useState(false);
  const [unreadNotifCount, setUnreadNotifCount] = useState(0);
  const [notifPage, setNotifPage] = useState(1);
  const [notifHasMore, setNotifHasMore] = useState(true);
  const notifLoaded = useRef(false);
  const [showNotifications, setShowNotifications] = useState(false);

  // Pagination for sales
  const [salesPage, setSalesPage] = useState(1);
  const [salesHasMore, setSalesHasMore] = useState(false);
  const salesPerPage = 20;

  // Load all data
  const loadData = async () => {
    try {
      const [profileRes, assetsRes, statsRes, affiliateRes] = await Promise.all([
        creatorApi.getProfile(),
        creatorApi.getAssets(),
        creatorApi.getStats(),
        creatorApi.getMyAffiliateStats(),
      ]);
      setProfile(profileRes.data);
      setAssets(assetsRes.data.results || assetsRes.data || []);
      setStats(statsRes.data);
      setAffiliateStats(affiliateRes.data);
    } catch (err) {
      console.error(err);
      showToast("Failed to load creator data", "error");
    }
  };

  const loadSales = async (page = 1, append = false) => {
    try {
      const res = await creatorApi.getSales({ page, page_size: salesPerPage });
      const results = res.data.results || res.data || [];
      if (append) {
        setSales(prev => [...prev, ...results]);
      } else {
        setSales(results);
      }
      setSalesHasMore(!!res.data.next);
      setSalesPage(page);
    } catch (err) {
      showToast("Failed to load sales", "error");
    }
  };

  const loadDiscounts = async () => {
    if (!assets.length) return;
    // For simplicity, load discounts for first asset? Better to have asset selector.
    // We'll implement later.
  };

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

  // Delete asset
  const handleDeleteAsset = async () => {
    if (!confirmState.assetId) return;
    try {
      await creatorApi.deleteAsset(confirmState.assetId);
      setAssets(prev => prev.filter(a => a.id !== confirmState.assetId));
      showToast("Asset deleted", "success");
      loadData(); // refresh stats
    } catch {
      showToast("Delete failed", "error");
    } finally {
      setConfirmState({ isOpen: false, action: null, assetId: null, discountId: null });
    }
  };

  // Delete discount
  const handleDeleteDiscount = async () => {
    // Placeholder
    showToast("Discount deletion not implemented", "error");
    setConfirmState({ isOpen: false, action: null, assetId: null, discountId: null });
  };

  // Create discount
  const handleCreateDiscount = async (e) => {
    e.preventDefault();
    try {
      // Assuming first asset for demo; proper implementation would select asset.
      const assetId = assets[0]?.id;
      if (!assetId) { showToast("No asset to attach discount", "error"); return; }
      await creatorApi.createDiscountCode(assetId, newDiscount);
      showToast("Discount code created", "success");
      setShowDiscountForm(false);
      setNewDiscount({ code: "", discount_type: "percent", discount_value: "", max_uses: 1, valid_to: "" });
      loadDiscounts();
    } catch {
      showToast("Failed to create discount", "error");
    }
  };

  // Toggle asset active status
  const toggleAssetStatus = async (assetId, currentStatus) => {
    try {
      await creatorApi.updateAsset(assetId, { is_active: !currentStatus });
      setAssets(prev => prev.map(a => a.id === assetId ? { ...a, is_active: !currentStatus } : a));
      showToast(`Asset ${!currentStatus ? "activated" : "deactivated"}`, "success");
    } catch {
      showToast("Status change failed", "error");
    }
  };

  // Copy shareable link to clipboard
  const copyShareLink = (slug) => {
    const url = `${window.location.origin}/creator/pay/${slug}`;
    navigator.clipboard.writeText(url);
    showToast("Link copied to clipboard", "success");
  };

  // Show toast
  const showToast = useCallback((msg, type = "success") => {
    const id = ++toastId.current;
    setToasts(prev => [...prev, { id, message: msg, type }]);
  }, []);
  const hideToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  // Initial loads
  useEffect(() => {
    loadData();
    loadSales(1, false);
  }, []);

  useEffect(() => {
    if (!notifLoaded.current && !loading) {
      notifLoaded.current = true;
      loadNotifications(1, true);
      loadUnreadCount();
    }
  }, [loading]);

  useEffect(() => {
    const handler = (e) => {
      if (settingsDropRef.current && !settingsDropRef.current.contains(e.target)) {
        setSettingsDropOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const navItems = [
    { id: "overview", label: "Overview" },
    { id: "assets", label: "My Links" },
    { id: "sales", label: "Sales" },
    { id: "affiliate", label: "Affiliate" },
    { id: "discounts", label: "Discounts" },
    { id: "settings", label: "Settings" },
  ];

  if (loading) {
    return <div className={styles.loading}>Loading creator dashboard…</div>;
  }

  return (
    <div className={styles.root}>
      {/* Sidebar */}
      <aside className={`${styles.sidebar} ${sidebarOpen ? styles.sidebarOpen : ""}`}>
        <div className={styles.sidebarHead}>
          <a href="/" className={styles.logo}>
            <span className={styles.logoMark}>C</span>
            <span className={styles.logoText}>Creator</span>
          </a>
          <button className={styles.sidebarClose} onClick={() => setSidebarOpen(false)}>✕</button>
        </div>
        <nav className={styles.nav}>
          <div className={styles.navGroup}>
            {navItems.map(item => (
              <button
                key={item.id}
                className={`${styles.navItem} ${activeTab === item.id ? styles.navActive : ""}`}
                onClick={() => { setActiveTab(item.id); setSidebarOpen(false); }}
              >
                <span>{item.label}</span>
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
              <span className={styles.userName}>{profile?.display_name || user?.email}</span>
              <span className={styles.userRole}>Creator</span>
            </div>
          </div>
          <button className={styles.logoutBtn} onClick={() => logout().then(() => navigate("/login"))}>
            Sign out
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className={styles.main}>
        <header className={styles.topbar}>
          <button className={styles.menuBtn} onClick={() => setSidebarOpen(true)}>☰</button>
          <div className={styles.topbarLeft}>
            <h2 className={styles.pageTitle}>Creator Dashboard</h2>
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
                  <button onClick={() => navigate("/settings")}>Settings</button>
                  <button onClick={() => logout().then(() => navigate("/login"))}>Sign out</button>
                </div>
              )}
            </div>
          </div>
        </header>

        <div className={styles.content}>
          {activeTab === "overview" && (
            <div className={styles.fadeIn}>
              <div className={styles.welcomeBar}>
                <div>
                  <h3 className={styles.welcomeTitle}>Creator overview</h3>
                  <p className={styles.welcomeSub}>Manage your payable links and track earnings.</p>
                </div>
                <button onClick={() => navigate("/creator/assets/new")} className={styles.primaryButton}>
                  + New payable link
                </button>
              </div>

              <div className={styles.statsRow}>
                <div className={styles.statCard}>
                  <div className={styles.statCardLabel}>Total revenue</div>
                  <div className={styles.statCardVal}>{stats?.total_revenue_usd || "$0"}</div>
                </div>
                <div className={styles.statCard}>
                  <div className={styles.statCardLabel}>Net earnings</div>
                  <div className={styles.statCardVal}>{stats?.total_net_usd || "$0"}</div>
                </div>
                <div className={styles.statCard}>
                  <div className={styles.statCardLabel}>Total sales</div>
                  <div className={styles.statCardVal}>{stats?.total_sales || 0}</div>
                </div>
                <div className={styles.statCard}>
                  <div className={styles.statCardLabel}>Active links</div>
                  <div className={styles.statCardVal}>{assets.filter(a => a.is_active).length}</div>
                </div>
              </div>

              <div className={styles.recentSection}>
                <div className={styles.sectionHeader}>
                  <h3>Recent sales</h3>
                  <button onClick={() => setActiveTab("sales")} className={styles.linkButton}>View all →</button>
                </div>
                {sales.length === 0 ? (
                  <div className={styles.emptyState}>No sales yet. Create a link and share it.</div>
                ) : (
                  sales.slice(0, 5).map(sale => (
                    <div key={sale.id} className={styles.saleRow}>
                      <div className={styles.saleInfo}>
                        <div className={styles.saleTitle}>{sale.asset_title}</div>
                        <div className={styles.saleBuyer}>{sale.buyer_email}</div>
                      </div>
                      <div className={styles.saleAmount}>{formatUSD(sale.amount_usd)}</div>
                      <div className={styles.saleDate}>{shortDate(sale.created_at)}</div>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {activeTab === "assets" && (
            <div className={styles.fadeIn}>
              <div className={styles.sectionHeader}>
                <h3>Your payable links</h3>
                <button onClick={() => navigate("/creator/assets/new")} className={styles.primaryButton}>
                  + New link
                </button>
              </div>
              {assets.length === 0 ? (
                <div className={styles.emptyState}>No payable links yet. Create your first one.</div>
              ) : (
                <div className={styles.assetsList}>
                  {assets.map(asset => (
                    <div key={asset.id} className={styles.assetCard}>
                      <div className={styles.assetHeader}>
                        <div className={styles.assetTitle}>{asset.title}</div>
                        <div className={styles.assetStatus}>
                          {asset.is_active ? (
                            <span className={styles.badgeActive}>Active</span>
                          ) : (
                            <span className={styles.badgeInactive}>Inactive</span>
                          )}
                        </div>
                      </div>
                      <div className={styles.assetMeta}>
                        <span>💰 {formatUSD(asset.price_usd || 0)}</span>
                        <span>📦 {asset.total_sales || 0} sales</span>
                        <span>🔗 /c/{asset.slug}</span>
                      </div>
                      <div className={styles.assetActions}>
                        <button onClick={() => toggleAssetStatus(asset.id, asset.is_active)}>
                          {asset.is_active ? "Deactivate" : "Activate"}
                        </button>
                        <button onClick={() => copyShareLink(asset.slug)}>Copy link</button>
                        <button onClick={() => navigate(`/creator/assets/${asset.id}`)}>Edit</button>
                        <button onClick={() => setConfirmState({ isOpen: true, action: "deleteAsset", assetId: asset.id })}>Delete</button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {activeTab === "sales" && (
            <div className={styles.fadeIn}>
              <div className={styles.sectionHeader}>
                <h3>Sales history</h3>
              </div>
              {sales.length === 0 ? (
                <div className={styles.emptyState}>No sales recorded yet.</div>
              ) : (
                <>
                  <table className={styles.salesTable}>
                    <thead>
                      <tr>
                        <th>Asset</th>
                        <th>Buyer</th>
                        <th>Amount</th>
                        <th>Net</th>
                        <th>Date</th>
                       </tr>
                    </thead>
                    <tbody>
                      {sales.map(sale => (
                        <tr key={sale.id}>
                          <td>{sale.asset_title}</td>
                          <td>{sale.buyer_email}</td>
                          <td>{formatUSD(sale.amount_usd)}</td>
                          <td>{formatUSD(sale.net_usd)}</td>
                          <td>{new Date(sale.created_at).toLocaleDateString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {salesHasMore && (
                    <button onClick={() => loadSales(salesPage + 1, true)} className={styles.loadMoreBtn}>
                      Load more
                    </button>
                  )}
                </>
              )}
            </div>
          )}

          {activeTab === "affiliate" && (
            <div className={styles.fadeIn}>
              <div className={styles.sectionHeader}>
                <h3>Affiliate program</h3>
              </div>
              {affiliateStats ? (
                <div className={styles.affiliateStats}>
                  <div className={styles.statCard}>
                    <div className={styles.statCardLabel}>Affiliate code</div>
                    <div className={styles.statCardVal}>{affiliateStats.affiliate_code || "Not generated"}</div>
                    {!affiliateStats.affiliate_code && (
                      <button onClick={() => creatorApi.generateAffiliateCode().then(() => loadData())} className={styles.secondaryButton}>
                        Generate code
                      </button>
                    )}
                  </div>
                  <div className={styles.statCard}>
                    <div className={styles.statCardLabel}>Clicks</div>
                    <div className={styles.statCardVal}>{affiliateStats.clicks || 0}</div>
                  </div>
                  <div className={styles.statCard}>
                    <div className={styles.statCardLabel}>Conversions</div>
                    <div className={styles.statCardVal}>{affiliateStats.conversions || 0}</div>
                  </div>
                  <div className={styles.statCard}>
                    <div className={styles.statCardLabel}>Earnings</div>
                    <div className={styles.statCardVal}>{formatUSD(affiliateStats.earnings_usd || 0)}</div>
                  </div>
                </div>
              ) : (
                <div className={styles.emptyState}>No affiliate data yet.</div>
              )}
            </div>
          )}

          {activeTab === "discounts" && (
            <div className={styles.fadeIn}>
              <div className={styles.sectionHeader}>
                <h3>Discount codes</h3>
                <button onClick={() => setShowDiscountForm(!showDiscountForm)} className={styles.primaryButton}>
                  + Add discount
                </button>
              </div>
              {showDiscountForm && (
                <form onSubmit={handleCreateDiscount} className={styles.discountForm}>
                  <input type="text" placeholder="Code (e.g., SAVE10)" value={newDiscount.code} onChange={e => setNewDiscount({...newDiscount, code: e.target.value.toUpperCase()})} required />
                  <select value={newDiscount.discount_type} onChange={e => setNewDiscount({...newDiscount, discount_type: e.target.value})}>
                    <option value="percent">Percentage (%)</option>
                    <option value="fixed">Fixed amount ($)</option>
                  </select>
                  <input type="number" placeholder="Value" value={newDiscount.discount_value} onChange={e => setNewDiscount({...newDiscount, discount_value: e.target.value})} required />
                  <input type="number" placeholder="Max uses" value={newDiscount.max_uses} onChange={e => setNewDiscount({...newDiscount, max_uses: e.target.value})} />
                  <input type="date" placeholder="Valid until" value={newDiscount.valid_to} onChange={e => setNewDiscount({...newDiscount, valid_to: e.target.value})} />
                  <button type="submit" className={styles.saveBtn}>Create</button>
                </form>
              )}
              <div className={styles.emptyState}>Discount code management coming soon. For now, use admin panel.</div>
            </div>
          )}

          {activeTab === "settings" && (
            <div className={styles.fadeIn}>
              <div className={styles.settingsPanel}>
                <h3>Payout wallet</h3>
                <div className={styles.walletInfo}>
                  {profile?.custom_payout_wallet ? (
                    <>
                      <span className={styles.walletAddress}>{truncateWallet(profile.custom_payout_wallet, 12)}</span>
                      <span className={styles.walletMeta}>
                        {profile.custom_payout_blockchain || "TRX"} · {profile.custom_payout_currency || "USDT"}
                      </span>
                    </>
                  ) : (
                    <span className={styles.walletFallback}>Using your default CashSpace wallet</span>
                  )}
                </div>
                <button onClick={() => navigate("/creator/settings")} className={styles.secondaryButton}>
                  Edit settings
                </button>
              </div>
            </div>
          )}
        </div>
      </main>

      {sidebarOpen && <div className={styles.overlay} onClick={() => setSidebarOpen(false)} />}
      <ConfirmModal
        isOpen={confirmState.isOpen && confirmState.action === "deleteAsset"}
        title="Delete payable link"
        message="Are you sure? This cannot be undone."
        onConfirm={handleDeleteAsset}
        onCancel={() => setConfirmState({ isOpen: false, action: null, assetId: null })}
      />
      <div className={styles.toastStack}>
        {toasts.map(t => <Toast key={t.id} message={t.message} type={t.type} onClose={() => hideToast(t.id)} />)}
      </div>
    </div>
  );
}