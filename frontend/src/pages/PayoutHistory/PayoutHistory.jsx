// frontend/src/pages/PayoutHistory.jsx
import React, { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import { formatUSD, shortDate, truncateWallet } from "../../utils/formatters";
import styles from "./PayoutHistory.module.css";

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

export default function PayoutHistory() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [payouts, setPayouts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [toasts, setToasts] = useState([]);
  const toastId = useRef(0);

  const showToast = useCallback((msg, type = "error") => {
    const id = ++toastId.current;
    setToasts(prev => [...prev, { id, message: msg, type }]);
  }, []);
  const hideToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  const fetchPayouts = async (pageNum = 1, append = false) => {
    try {
      const res = await fetch(`/api/v1/payments/payout-history/?page=${pageNum}&page_size=20`, {
        headers: { Authorization: `Bearer ${localStorage.getItem("access_token")}` }
      });
      if (!res.ok) throw new Error("Failed to fetch payouts");
      const data = await res.json();
      const results = data.results || data || [];
      if (append) {
        setPayouts(prev => [...prev, ...results]);
      } else {
        setPayouts(results);
      }
      setHasMore(!!data.next);
      setPage(pageNum);
    } catch (err) {
      showToast("Failed to load payout history", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPayouts(1, false);
  }, []);

  if (loading && payouts.length === 0) {
    return <div className={styles.loading}>Loading payout history...</div>;
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1>Payout History</h1>
        <button onClick={() => navigate(-1)} className={styles.backButton}>← Back</button>
      </div>

      {payouts.length === 0 ? (
        <div className={styles.emptyState}>No payouts recorded yet.</div>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Date</th>
                <th>Amount (Crypto)</th>
                <th>Amount (USD)</th>
                <th>Blockchain</th>
                <th>Wallet</th>
                <th>Status</th>
                <th>Tx ID</th>
              </tr>
            </thead>
            <tbody>
              {payouts.map(p => (
                <tr key={p.id}>
                  <td>{shortDate(p.created_at)}</td>
                  <td>{p.payout_crypto_amount} {p.currency_code}</td>
                  <td>{formatUSD(p.payout_usd_equivalent)}</td>
                  <td>{p.blockchain_code}</td>
                  <td className={styles.mono}>{truncateWallet(p.destination_wallet)}</td>
                  <td>
                    <span className={`${styles.status} ${styles[p.payout_status]}`}>
                      {p.payout_status}
                    </span>
                  </td>
                  <td className={styles.mono}>{truncateWallet(p.tx_hash || p.payram_payout_id, 12)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {hasMore && (
            <div className={styles.loadMore}>
              <button onClick={() => fetchPayouts(page + 1, true)} className={styles.loadMoreBtn}>
                Load more
              </button>
            </div>
          )}
        </div>
      )}

      <div className={styles.toastStack}>
        {toasts.map(t => <Toast key={t.id} message={t.message} type={t.type} onClose={() => hideToast(t.id)} />)}
      </div>
    </div>
  );
}