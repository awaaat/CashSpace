// frontend/src/pages/Admin/AdminCreators.jsx
import React, { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import { formatUSD, shortDate, truncateWallet } from "../../utils/formatters";
import styles from "./AdminCreators.module.css";

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

export default function AdminCreators() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [creators, setCreators] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [selectedCreator, setSelectedCreator] = useState(null);
  const [showDetail, setShowDetail] = useState(false);
  const [toasts, setToasts] = useState([]);
  const [confirmState, setConfirmState] = useState({ isOpen: false, action: null, creatorId: null });
  const toastId = useRef(0);

  const showToast = useCallback((msg, type = "success") => {
    const id = ++toastId.current;
    setToasts(prev => [...prev, { id, message: msg, type }]);
  }, []);
  const hideToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  const fetchCreators = async () => {
    setLoading(true);
    try {
      // Adjust endpoint to your backend – e.g., GET /api/v1/creator/admin/
      const res = await fetch("/api/v1/creator/admin/", {
        headers: { Authorization: `Bearer ${localStorage.getItem("access_token")}` }
      });
      if (!res.ok) throw new Error("Failed to fetch");
      const data = await res.json();
      setCreators(data.results || data || []);
    } catch (err) {
      showToast("Failed to load creators", "error");
    } finally {
      setLoading(false);
    }
  };

  const updateCreator = async (id, updates) => {
    try {
      const res = await fetch(`/api/v1/creator/admin/${id}/`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("access_token")}`
        },
        body: JSON.stringify(updates)
      });
      if (!res.ok) throw new Error("Update failed");
      const updated = await res.json();
      setCreators(prev => prev.map(c => c.id === id ? updated : c));
      showToast("Creator updated", "success");
    } catch {
      showToast("Update failed", "error");
    }
  };

  useEffect(() => {
    fetchCreators();
  }, []);

  const handleVerify = (id, currentStatus) => {
    setConfirmState({
      isOpen: true,
      action: "verify",
      creatorId: id,
      message: currentStatus ? "Unverify this creator?" : "Verify this creator?"
    });
  };

  const handleActivate = (id, currentActive) => {
    setConfirmState({
      isOpen: true,
      action: "activate",
      creatorId: id,
      message: currentActive ? "Suspend this creator?" : "Activate this creator?"
    });
  };

  const confirmAction = async () => {
    const { action, creatorId } = confirmState;
    if (action === "verify") {
      const creator = creators.find(c => c.id === creatorId);
      await updateCreator(creatorId, { is_verified: !creator.is_verified });
    } else if (action === "activate") {
      const creator = creators.find(c => c.id === creatorId);
      await updateCreator(creatorId, { is_active: !creator.is_active });
    }
    setConfirmState({ isOpen: false, action: null, creatorId: null });
  };

  const filteredCreators = creators.filter(c => {
    if (filter === "verified" && !c.is_verified) return false;
    if (filter === "unverified" && c.is_verified) return false;
    if (filter === "active" && !c.is_active) return false;
    if (filter === "suspended" && c.is_active) return false;
    if (search) {
      return c.display_name?.toLowerCase().includes(search.toLowerCase()) ||
             c.user_email?.toLowerCase().includes(search.toLowerCase());
    }
    return true;
  });

  if (loading) return <div className={styles.loading}>Loading creators...</div>;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1>Creators</h1>
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
            placeholder="Search by name or email"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className={styles.searchInput}
          />
          <button onClick={fetchCreators} className={styles.refreshBtn}>Refresh</button>
        </div>
      </div>

      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Display Name</th>
              <th>Email</th>
              <th>Assets</th>
              <th>Sales</th>
              <th>Revenue</th>
              <th>Verified</th>
              <th>Active</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredCreators.map(c => (
              <tr key={c.id}>
                <td className={styles.bold}>{c.display_name || "—"}</td>
                <td>{c.user_email}</td>
                <td>{c.total_assets || 0}</td>
                <td>{c.total_sales || 0}</td>
                <td>{formatUSD(c.total_revenue_usd || 0)}</td>
                <td>
                  <span className={c.is_verified ? styles.badgeVerified : styles.badgeUnverified}>
                    {c.is_verified ? "Verified" : "Unverified"}
                  </span>
                </td>
                <td>
                  <span className={c.is_active ? styles.badgeActive : styles.badgeInactive}>
                    {c.is_active ? "Active" : "Suspended"}
                  </span>
                </td>
                <td>
                  <button onClick={() => { setSelectedCreator(c); setShowDetail(true); }} className={styles.actionBtn}>View</button>
                  <button onClick={() => handleVerify(c.id, c.is_verified)} className={styles.actionBtn}>
                    {c.is_verified ? "Unverify" : "Verify"}
                  </button>
                  <button onClick={() => handleActivate(c.id, c.is_active)} className={styles.actionBtn}>
                    {c.is_active ? "Suspend" : "Activate"}
                  </button>
                </td>
              </tr>
            ))}
            {filteredCreators.length === 0 && (
              <tr><td colSpan="8" className={styles.empty}>No creators found</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {showDetail && selectedCreator && (
        <div className={styles.modalOverlay} onClick={() => setShowDetail(false)}>
          <div className={styles.detailModal} onClick={e => e.stopPropagation()}>
            <div className={styles.modalHeader}>
              <h2>{selectedCreator.display_name || selectedCreator.user_email}</h2>
              <button onClick={() => setShowDetail(false)}>×</button>
            </div>
            <div className={styles.detailBody}>
              <div><strong>User ID:</strong> {selectedCreator.user_id}</div>
              <div><strong>Email:</strong> {selectedCreator.user_email}</div>
              <div><strong>Bio:</strong> {selectedCreator.bio || "—"}</div>
              <div><strong>Payout wallet:</strong> <code>{selectedCreator.custom_payout_wallet || "Default wallet"}</code></div>
              <div><strong>Blockchain:</strong> {selectedCreator.custom_payout_blockchain || "TRX"}</div>
              <div><strong>Currency:</strong> {selectedCreator.custom_payout_currency || "USDT"}</div>
              <div><strong>Commission rate override:</strong> {selectedCreator.commission_rate_override ? `${selectedCreator.commission_rate_override * 100}%` : "Global"}</div>
              <div><strong>Total assets:</strong> {selectedCreator.total_assets || 0}</div>
              <div><strong>Total sales:</strong> {selectedCreator.total_sales || 0}</div>
              <div><strong>Total revenue:</strong> {formatUSD(selectedCreator.total_revenue_usd || 0)}</div>
              <div><strong>Joined:</strong> {shortDate(selectedCreator.created_at)}</div>
            </div>
          </div>
        </div>
      )}

      <ConfirmModal
        isOpen={confirmState.isOpen}
        title="Confirm Action"
        message={confirmState.message}
        onConfirm={confirmAction}
        onCancel={() => setConfirmState({ isOpen: false, action: null, creatorId: null })}
      />

      <div className={styles.toastStack}>
        {toasts.map(t => <Toast key={t.id} message={t.message} type={t.type} onClose={() => hideToast(t.id)} />)}
      </div>
    </div>
  );
}