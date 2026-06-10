// frontend/src/pages/Creator/PublicAssetPage.jsx
import React, { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { creatorApi } from "../../api/creator";
import styles from "./PublicAssetPage.module.css";

// Toast component
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

export default function PublicAssetPage() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const [asset, setAsset] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [checkoutLoading, setCheckoutLoading] = useState(false);
  const [toasts, setToasts] = useState([]);
  const [form, setForm] = useState({
    email: "",
    full_name: "",
    amount_usd: "",
  });

  useEffect(() => {
    const fetchAsset = async () => {
      try {
        const res = await creatorApi.getAsset(slug);
        setAsset(res.data);
      } catch (err) {
        if (err.response?.status === 404) setError("Asset not found");
        else if (err.response?.status === 410) setError("This asset is sold out");
        else setError("Failed to load asset");
      } finally {
        setLoading(false);
      }
    };
    fetchAsset();
  }, [slug]);

  const showToast = (msg, type = "success") => {
    const id = Date.now();
    setToasts(prev => [...prev, { id, message: msg, type }]);
  };
  const hideToast = (id) => setToasts(prev => prev.filter(t => t.id !== id));

  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.email) {
      showToast("Email is required", "error");
      return;
    }
    if (asset.pricing_type === "pwyw") {
      const amount = parseFloat(form.amount_usd);
      if (isNaN(amount) || amount < parseFloat(asset.min_price_usd)) {
        showToast(`Minimum amount is $${asset.min_price_usd}`, "error");
        return;
      }
    }
    setCheckoutLoading(true);
    try {
      const payload = {
        email: form.email,
        full_name: form.full_name,
      };
      if (asset.pricing_type === "pwyw") {
        payload.amount_usd = parseFloat(form.amount_usd);
      }
      const res = await creatorApi.checkout(slug, payload);
      // Redirect to PayRam payment URL
      window.location.href = res.data.payment_url;
    } catch (err) {
      const msg = err.response?.data?.error || "Checkout failed";
      showToast(msg, "error");
      setCheckoutLoading(false);
    }
  };

  if (loading) {
    return <div className={styles.container}><div className={styles.card}>Loading...</div></div>;
  }

  if (error) {
    return (
      <div className={styles.container}>
        <div className={styles.card}>
          <h1>Error</h1>
          <p>{error}</p>
          <button onClick={() => navigate("/")} className={styles.primaryButton}>Go home</button>
        </div>
      </div>
    );
  }

  const displayPrice = asset.pricing_type === "fixed" 
    ? `$${asset.price_usd}` 
    : `Pay what you want (min $${asset.min_price_usd})`;

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <div className={styles.header}>
          {asset.creator_avatar && <img src={asset.creator_avatar} alt={asset.creator_name} className={styles.avatar} />}
          <div>
            <h1>{asset.title}</h1>
            <p className={styles.creator}>by {asset.creator_name}</p>
          </div>
        </div>
        <p className={styles.description}>{asset.description}</p>
        <div className={styles.price}>{displayPrice}</div>

        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.field}>
            <label>Email *</label>
            <input
              type="email"
              name="email"
              value={form.email}
              onChange={handleChange}
              required
              placeholder="you@example.com"
            />
          </div>
          <div className={styles.field}>
            <label>Full name (optional)</label>
            <input
              type="text"
              name="full_name"
              value={form.full_name}
              onChange={handleChange}
              placeholder="John Doe"
            />
          </div>
          {asset.pricing_type === "pwyw" && (
            <div className={styles.field}>
              <label>Amount (USD)</label>
              <input
                type="number"
                name="amount_usd"
                value={form.amount_usd}
                onChange={handleChange}
                step="0.01"
                min={asset.min_price_usd}
                placeholder={asset.min_price_usd}
                required
              />
            </div>
          )}
          <button type="submit" className={styles.primaryButton} disabled={checkoutLoading}>
            {checkoutLoading ? "Processing..." : `Pay ${asset.pricing_type === "fixed" ? `$${asset.price_usd}` : ""}`}
          </button>
        </form>

        <div className={styles.footer}>
          <p>Secure payment via card or crypto. You will receive access immediately after payment.</p>
        </div>
      </div>
      <div className={styles.toastStack}>
        {toasts.map(t => <Toast key={t.id} message={t.message} type={t.type} onClose={() => hideToast(t.id)} />)}
      </div>
    </div>
  );
}