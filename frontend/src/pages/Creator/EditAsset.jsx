// frontend/src/pages/Creator/EditAsset.jsx
import React, { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import { creatorApi } from "../../api/creator";
import styles from "./CreateAsset.module.css"; // reuses same styling

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

export default function EditAsset() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [toasts, setToasts] = useState([]);
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

  const showToast = (msg, type = "success") => {
    const id = Date.now();
    setToasts(prev => [...prev, { id, message: msg, type }]);
  };
  const hideToast = (id) => setToasts(prev => prev.filter(t => t.id !== id));

  useEffect(() => {
    const fetchAsset = async () => {
      try {
        const res = await creatorApi.getAsset(id);
        const asset = res.data;
        setForm({
          title: asset.title || "",
          description: asset.description || "",
          asset_type: asset.asset_type || "url",
          unlock_value: asset.unlock_value || "",
          pricing_type: asset.pricing_type || "fixed",
          price_usd: asset.price_usd ? String(asset.price_usd) : "",
          min_price_usd: asset.min_price_usd ? String(asset.min_price_usd) : "5",
          is_active: asset.is_active !== false,
        });
      } catch (err) {
        console.error(err);
        showToast("Failed to load asset", "error");
        navigate("/creator");
      } finally {
        setLoading(false);
      }
    };
    fetchAsset();
  }, [id, navigate]);

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
    setSaving(true);
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
      await creatorApi.updateAsset(id, payload);
      showToast("Payable link updated", "success");
      setTimeout(() => navigate("/creator"), 1500);
    } catch (err) {
      console.error(err);
      const msg = err.response?.data?.detail || "Failed to update asset";
      showToast(msg, "error");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className={styles.container}><div className={styles.card}>Loading asset...</div></div>;
  }

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <h1>Edit payable link</h1>
        <p className={styles.subtitle}>Update your content, price, or availability.</p>

        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.field}>
            <label>Title *</label>
            <input
              type="text"
              name="title"
              value={form.title}
              onChange={handleChange}
              required
            />
          </div>

          <div className={styles.field}>
            <label>Description (optional)</label>
            <textarea
              name="description"
              value={form.description}
              onChange={handleChange}
              rows="3"
            />
          </div>

          <div className={styles.fieldGroup}>
            <div className={styles.field}>
              <label>Asset type</label>
              <select name="asset_type" value={form.asset_type} onChange={handleChange}>
                <option value="url">External URL</option>
                <option value="file">File download</option>
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
                required
              />
            ) : (
              <textarea
                name="unlock_value"
                value={form.unlock_value}
                onChange={handleChange}
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
            <button type="submit" className={styles.primaryButton} disabled={saving}>
              {saving ? "Saving..." : "Save changes"}
            </button>
          </div>
        </form>
      </div>

      <div className={styles.toastStack}>
        {toasts.map(t => <Toast key={t.id} message={t.message} type={t.type} onClose={() => hideToast(t.id)} />)}
      </div>
    </div>
  );
}