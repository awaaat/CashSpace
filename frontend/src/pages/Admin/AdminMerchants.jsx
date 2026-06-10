// frontend/src/pages/Admin/AdminMerchants.jsx
import React, { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import { authApi } from "../../api/auth";
import { formatUSD, shortDate, truncateWallet } from "../../utils/formatters";
import styles from "./AdminMerchants.module.css";

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

function ConfirmModal({ isOpen, title, message, onConfirm, onCancel }) {
  if (!isOpen) return null;
  return (
    <div className={styles.modalOverlay} onClick={onCancel}>
      <div className={styles.confirmModal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.confirmHeader}>
          <h3>{title}</h3>
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

export default function AdminMerchants() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [merchants, setMerchants] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [selectedMerchant, setSelectedMerchant] = useState(null);
  const [showDetail, setShowDetail] = useState(false);
  const [toasts, setToasts] = useState([]);
  const [confirmState, setConfirmState] = useState({ isOpen: false, action: null, merchantId: null });
  const toastId = useRef(0);

  const showToast = useCallback((msg, type = "success") => {
    const id = ++toastId.current;
    setToasts(prev => [...prev, { id, message: msg, type }]);
  }, []);
  const hideToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  // API calls (adjust endpoints as needed)
  const fetchMerchants = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/v1/merchants/admin/", {
        headers: { Authorization: `Bearer ${localStorage.getItem("access_token")}` }
      });
      if (!res.ok) throw new Error("Failed to fetch");
      const data = await res.json();
      setMerchants(data.results || data || []);
    } catch (err) {
      showToast("Failed to load merchants", "error");
    } finally {
      setLoading(false);
    }
  };

  const updateMerchant = async (id, updates) => {
    try {
      const res = await fetch(`/api/v1/merchants/admin/${id}/`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("access_token")}`
        },
        body: JSON.stringify(updates)
      });
      if (!res.ok) throw new Error("Update failed");
      const updated = await res.json();
      setMerchants(prev => prev.map(m => m.id === id ? updated : m));
      showToast("Merchant updated", "success");
    } catch {
      showToast("Update failed", "error");
    }
  };

  useEffect(() => {
    fetchMerchants();
  }, []);

  const handleVerify = (id, currentStatus) => {
    setConfirmState({
      isOpen: true,
      action: "verify",
      merchantId: id,
      message: currentStatus ? "Unverify this merchant?" : "Verify this merchant?"
    });
  };

  const handleActivate = (id, currentActive) => {
    setConfirmState({
      isOpen: true,
      action: "activate",
      merchantId: id,
      message: currentActive ? "Suspend this merchant?" : "Activate this merchant?"
    });
  };

  const confirmAction = async () => {
    const { action, merchantId } = confirmState;
    if (action === "verify") {
      const merchant = merchants.find(m => m.id === merchantId);
      await updateMerchant(merchantId, { is_verified: !merchant.is_verified });
    } else if (action === "activate") {
      const merchant = merchants.find(m => m.id === merchantId);
      await updateMerchant(merchantId, { is_active: !merchant.is_active });
    }
    setConfirmState({ isOpen: false, action: null, merchantId: null });
  };

  const filteredMerchants = merchants.filter(m => {
    if (filter === "verified" && !m.is_verified) return false;
    if (filter === "unverified" && m.is_verified) return false;
    if (filter === "active" && !m.is_active) return false;
    if (filter === "suspended" && m.is_active) return false;
    if (search) {
      return m.business_name?.toLowerCase().includes(search.toLowerCase()) ||
             m.user_email?.toLowerCase().includes(search.toLowerCase());
    }
    return true;
  });

  if (loading) return <div className={styles.loading}>Loading merchants...</div>;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1>Merchants</h1>
        <button onClick={() => navigate("/admin")} className={styles.backButton}>← Back to Admin</button>
      </div>

      <div className={styles.controls}>
        <div className={styles.filters}>
          <label>Filter:</label>
          <select value={filter} onChange={e => setFilter(e.target.value)}>
            <option value="all">All</option>
            <option value="verified">Verified</option>
            <option value="unverified">Unverified</option>
            <option value="active">Active</option>
            <option value="suspended">Suspended</option>
          </select>
          <input
            type="text"
            placeholder="Search by business or email"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className={styles.searchInput}
          />
          <button onClick={fetchMerchants} className={styles.refreshBtn}>Refresh</button>
        </div>
      </div>

      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Business</th>
              <th>Owner</th>
              <th>Settlement</th>
              <th>Sales</th>
              <th>Verified</th>
              <th>Active</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredMerchants.map(m => (
              <tr key={m.id}>
                <td className={styles.bold}>{m.business_name}</td>
                <td>{m.user_email}</td>
                <td className={styles.mono}>{truncateWallet(m.settlement_wallet_address || "-", 8)}</td>
                <td>{m.total_sales || 0}</td>
                <td>
                  <span className={m.is_verified ? styles.badgeVerified : styles.badgeUnverified}>
                    {m.is_verified ? "Verified" : "Unverified"}
                  </span>
                </td>
                <td>
                  <span className={m.is_active ? styles.badgeActive : styles.badgeInactive}>
                    {m.is_active ? "Active" : "Suspended"}
                  </span>
                </td>
                <td>
                  <button onClick={() => { setSelectedMerchant(m); setShowDetail(true); }} className={styles.actionBtn}>View</button>
                  <button onClick={() => handleVerify(m.id, m.is_verified)} className={styles.actionBtn}>
                    {m.is_verified ? "Unverify" : "Verify"}
                  </button>
                  <button onClick={() => handleActivate(m.id, m.is_active)} className={styles.actionBtn}>
                    {m.is_active ? "Suspend" : "Activate"}
                  </button>
                </td>
              </tr>
            ))}
            {filteredMerchants.length === 0 && (
              <tr><td colSpan="7" className={styles.empty}>No merchants found</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {showDetail && selectedMerchant && (
        <div className={styles.modalOverlay} onClick={() => setShowDetail(false)}>
          <div className={styles.detailModal} onClick={e => e.stopPropagation()}>
            <div className={styles.modalHeader}>
              <h2>{selectedMerchant.business_name}</h2>
              <button onClick={() => setShowDetail(false)}>×</button>
            </div>
            <div className={styles.detailBody}>
              <div><strong>Owner:</strong> {selectedMerchant.user_email}</div>
              <div><strong>Slug:</strong> {selectedMerchant.slug}</div>
              <div><strong>Description:</strong> {selectedMerchant.description || "—"}</div>
              <div><strong>Settlement blockchain:</strong> {selectedMerchant.settlement_blockchain}</div>
              <div><strong>Settlement currency:</strong> {selectedMerchant.settlement_currency}</div>
              <div><strong>Wallet address:</strong> <code>{selectedMerchant.settlement_wallet_address || "Not set"}</code></div>
              <div><strong>Commission override:</strong> {selectedMerchant.commission_rate_override ? `${selectedMerchant.commission_rate_override * 100}%` : "Global"}</div>
              <div><strong>Webhook URL:</strong> {selectedMerchant.webhook_url || "—"}</div>
              <div><strong>Total sales:</strong> {selectedMerchant.total_sales || 0}</div>
              <div><strong>Total revenue:</strong> {formatUSD(selectedMerchant.total_revenue_usd || 0)}</div>
              <div><strong>Joined:</strong> {shortDate(selectedMerchant.created_at)}</div>
            </div>
          </div>
        </div>
      )}

      <ConfirmModal
        isOpen={confirmState.isOpen}
        title="Confirm Action"
        message={confirmState.message}
        onConfirm={confirmAction}
        onCancel={() => setConfirmState({ isOpen: false, action: null, merchantId: null })}
      />

      <div className={styles.toastStack}>
        {toasts.map(t => <Toast key={t.id} message={t.message} type={t.type} onClose={() => hideToast(t.id)} />)}
      </div>
    </div>
  );
}