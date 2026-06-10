import React, { useEffect, useState, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { usePayments } from "../hooks/usePayment";
import { authApi } from "../api/auth";
import { creatorApi } from "../api/creator";
import { merchantApi } from "../api/merchant";
import { formatUSD, shortDate, truncateWallet, statusColor } from "../utils/formatters";
import Sidebar from "../components/dashboard/Sidebar";
import Topbar from "../components/dashboard/Topbar";
import WelcomeBanner from "../components/dashboard/WelcomeBanner";
import StatsCards from "../components/dashboard/StatsCards";
import RoleCards from "../components/dashboard/RoleCards";
import RecentTransactions from "../components/dashboard/RecentTransactions";
import { ToastProvider, useToast } from "../components/ui/Toast";
import { ConfirmModalProvider } from "../components/ui/ConfirmModal";
import styles from "./UnifiedDashboard.module.css";

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

function ConfirmModal({ isOpen, title, message, onConfirm, onCancel }) {
  if (!isOpen) return null;
  return (
    <div className={styles.modalOverlay} onClick={onCancel}>
      <div className={styles.confirmModal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.confirmHeader}>
          <h3>{title || "Confirm Action"}</h3>
          <button className={styles.confirmClose} onClick={onCancel}>×</button>
        </div>
        <div className={styles.confirmBody}>{message}</div>
        <div className={styles.confirmFooter}>
          <button className={styles.confirmCancel} onClick={onCancel}>Cancel</button>
          <button className={styles.confirmOk} onClick={onConfirm}>OK</button>
        </div>
      </div>
    </div>
  );
}

function DashboardContent() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { payments, isLoading: paymentsLoading, fetchPayments } = usePayments();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [settingsDropOpen, setSettingsDropOpen] = useState(false);
  const settingsDropRef = useRef(null);

  // ── Notification panel outside-click ref ──
  const notifPanelRef = useRef(null);

  const [creatorProfile, setCreatorProfile] = useState(null);
  const [merchantProfile, setMerchantProfile] = useState(null);
  const [creatorStats, setCreatorStats] = useState(null);
  const [merchantStats, setMerchantStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [wallets, setWallets] = useState([]);
  const [toasts, setToasts] = useState([]);
  const toastId = useRef(0);
  const showToast = useCallback((msg, type = "success") => {
    const id = ++toastId.current;
    setToasts(prev => [...prev, { id, message: msg, type }]);
  }, []);
  const hideToast = useCallback((id) => setToasts(prev => prev.filter(t => t.id !== id)), []);

  const [notifications, setNotifications] = useState([]);
  const [notifLoading, setNotifLoading] = useState(false);
  const [unreadNotifCount, setUnreadNotifCount] = useState(0);
  const [notifPage, setNotifPage] = useState(1);
  const [notifHasMore, setNotifHasMore] = useState(true);
  const notifLoaded = useRef(false);
  const [showNotifications, setShowNotifications] = useState(false);

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

  // ── Fixed: verify backend confirmed the write before updating local state ──
  const markNotifRead = async (id) => {
    try {
      const res = await authApi.markNotificationRead(id);
      if (res.data?.is_read === true) {
        setNotifications(prev =>
          prev.map(n => n.id === id ? { ...n, is_read: true } : n)
        );
        setUnreadNotifCount(
          res.data.unread_count ?? Math.max(0, unreadNotifCount - 1)
        );
      } else {
        // Backend didn't confirm — re-fetch ground truth from DB
        await loadNotifications(1, true);
        await loadUnreadCount();
      }
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
    const loadData = async () => {
      setLoading(true);
      try {
        const [walletsRes, creatorRes, merchantRes, creatorStatsRes, merchantStatsRes] =
          await Promise.allSettled([
            authApi.getCryptoWallets(),
            creatorApi.getProfile(),
            merchantApi.getMe(),
            creatorApi.getStats(),
            merchantApi.getStats?.() || Promise.resolve({ data: null }),
          ]);
        if (walletsRes.status === "fulfilled")
          setWallets(walletsRes.value.data?.results || walletsRes.value.data || []);
        if (creatorRes.status === "fulfilled")
          setCreatorProfile(creatorRes.value.data);
        if (merchantRes.status === "fulfilled")
          setMerchantProfile(merchantRes.value.data);
        if (creatorStatsRes.status === "fulfilled")
          setCreatorStats(creatorStatsRes.value.data);
        if (merchantStatsRes.status === "fulfilled")
          setMerchantStats(merchantStatsRes.value.data);
      } catch (err) {
        console.error(err);
        showToast("Failed to load dashboard data", "error");
      } finally {
        setLoading(false);
      }
    };
    loadData();
    fetchPayments();
  }, []);

  useEffect(() => {
    if (!notifLoaded.current && !loading) {
      notifLoaded.current = true;
      loadNotifications(1, true);
      loadUnreadCount();
    }
  }, [loading]);

  // ── Settings dropdown outside-click ──
  useEffect(() => {
    const handler = (e) => {
      if (settingsDropRef.current && !settingsDropRef.current.contains(e.target)) {
        setSettingsDropOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // ── Notification panel outside-click ──
  useEffect(() => {
    const handler = (e) => {
      if (notifPanelRef.current && !notifPanelRef.current.contains(e.target)) {
        setShowNotifications(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const hasCreator = !!creatorProfile;
  const hasMerchant = !!merchantProfile;
  const recentPayments = payments.slice(0, 5);
  const totalSpent = payments
    .filter(p => p.status === "FILLED")
    .reduce((s, p) => s + (parseFloat(p.amount_usd) || 0), 0);

  if (loading) return <div className={styles.loading}>Loading dashboard…</div>;

  return (
    <>
      <Topbar
        user={user}
        notifications={notifications}
        unreadCount={unreadNotifCount}
        onNavigate={navigate}
        onLogout={logout}
        settingsDropOpen={settingsDropOpen}
        setSettingsDropOpen={setSettingsDropOpen}
        settingsDropRef={settingsDropRef}
        showNotifications={showNotifications}
        setShowNotifications={setShowNotifications}
        notifPanelRef={notifPanelRef}
        loadNotifications={loadNotifications}
        notifPage={notifPage}
        notifHasMore={notifHasMore}
        notifLoading={notifLoading}
        markNotifRead={markNotifRead}
        markAllNotifsRead={markAllNotifsRead}
      />
      <div className={styles.layout}>
        <Sidebar
          user={user}
          hasMerchant={hasMerchant}
          hasCreator={hasCreator}
          onNavigate={navigate}
          onLogout={logout}
          sidebarOpen={sidebarOpen}
          setSidebarOpen={setSidebarOpen}
        />
        <main className={styles.main}>
          <div className={styles.content}>
            <WelcomeBanner
              userName={user?.first_name || "there"}
              hasWallets={wallets.length > 0}
              onAddWallet={() => navigate("/wallets")}
            />
            <StatsCards
              totalSpent={totalSpent}
              merchantStats={merchantStats}
              creatorStats={creatorStats}
              hasMerchant={hasMerchant}
              hasCreator={hasCreator}
            />
            <RoleCards
              hasMerchant={hasMerchant}
              hasCreator={hasCreator}
              onNavigate={navigate}
            />
            <RecentTransactions
              payments={recentPayments}
              loading={paymentsLoading}
              onViewAll={() => navigate("/history")}
              onBuy={() => navigate("/buy")}
            />
          </div>
        </main>
      </div>
      <div className={styles.toastStack}>
        {toasts.map(t => (
          <Toast key={t.id} message={t.message} type={t.type} onClose={() => hideToast(t.id)} />
        ))}
      </div>
    </>
  );
}

export default function UnifiedDashboard() {
  return (
    <ConfirmModalProvider>
      <ToastProvider>
        <DashboardContent />
      </ToastProvider>
    </ConfirmModalProvider>
  );
}