// frontend/src/pages/Creator/CreatorSales.jsx
import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import { creatorApi } from "../../api/creator";
import { formatUSD, shortDate } from "../../utils/formatters";
import styles from "./CreatorSales.module.css";

function Toast({ message, type, onClose }) {
  React.useEffect(() => {
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

export default function CreatorSales() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [sales, setSales] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [toasts, setToasts] = useState([]);
  const [filter, setFilter] = useState("");

  const showToast = (msg, type = "error") => {
    const id = Date.now();
    setToasts(prev => [...prev, { id, message: msg, type }]);
  };
  const hideToast = (id) => setToasts(prev => prev.filter(t => t.id !== id));

  const loadSales = async (pageNum = 1, append = false) => {
    try {
      const params = { page: pageNum, page_size: 20 };
      if (filter) params.status = filter;
      const res = await creatorApi.getSales(params);
      const results = res.data.results || res.data || [];
      if (append) {
        setSales(prev => [...prev, ...results]);
      } else {
        setSales(results);
      }
      setHasMore(!!res.data.next);
      setPage(pageNum);
    } catch (err) {
      showToast("Failed to load sales", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSales(1, false);
  }, [filter]);

  const handleFilterChange = (e) => {
    setFilter(e.target.value);
    setLoading(true);
  };

  if (loading && sales.length === 0) {
    return <div className={styles.container}><div className={styles.card}>Loading sales...</div></div>;
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1>Sales history</h1>
        <button onClick={() => navigate("/creator")} className={styles.backButton}>← Back to dashboard</button>
      </div>

      <div className={styles.filters}>
        <label>Filter by status:</label>
        <select value={filter} onChange={handleFilterChange}>
          <option value="">All</option>
          <option value="completed">Completed</option>
          <option value="pending">Pending</option>
          <option value="failed">Failed</option>
          <option value="refunded">Refunded</option>
        </select>
      </div>

      {sales.length === 0 ? (
        <div className={styles.emptyState}>No sales found.</div>
      ) : (
        <table className={styles.salesTable}>
          <thead>
            <tr>
              <th>Date</th>
              <th>Asset</th>
              <th>Buyer</th>
              <th>Amount</th>
              <th>Net</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {sales.map(sale => (
              <tr key={sale.id}>
                <td>{shortDate(sale.created_at)}</td>
                <td>{sale.asset_title}</td>
                <td>{sale.buyer_email}</td>
                <td>{formatUSD(sale.amount_usd)}</td>
                <td>{formatUSD(sale.net_usd)}</td>
                <td><span className={`${styles.status} ${styles[sale.status]}`}>{sale.status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {hasMore && (
        <div className={styles.loadMore}>
          <button onClick={() => loadSales(page + 1, true)} className={styles.loadMoreBtn}>
            Load more
          </button>
        </div>
      )}

      <div className={styles.toastStack}>
        {toasts.map(t => <Toast key={t.id} message={t.message} type={t.type} onClose={() => hideToast(t.id)} />)}
      </div>
    </div>
  );
}