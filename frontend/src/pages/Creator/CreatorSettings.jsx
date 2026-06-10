// frontend/src/pages/Creator/CreatorSettings.jsx
import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import { creatorApi } from "../../api/creator";
import { authApi } from "../../api/auth";
import styles from "./CreatorSettings.module.css";

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

export default function CreatorSettings() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [toasts, setToasts] = useState([]);
  const [profile, setProfile] = useState({
    display_name: "",
    bio: "",
    custom_payout_wallet: "",
    custom_payout_blockchain: "TRX",
    custom_payout_currency: "USDT",
  });

  const showToast = (msg, type = "success") => {
    const id = Date.now();
    setToasts(prev => [...prev, { id, message: msg, type }]);
  };
  const hideToast = (id) => setToasts(prev => prev.filter(t => t.id !== id));

  useEffect(() => {
    const fetchProfile = async () => {
      try {
        const res = await creatorApi.getProfile();
        const data = res.data;
        setProfile({
          display_name: data.display_name || "",
          bio: data.bio || "",
          custom_payout_wallet: data.custom_payout_wallet || "",
          custom_payout_blockchain: data.custom_payout_blockchain || "TRX",
          custom_payout_currency: data.custom_payout_currency || "USDT",
        });
      } catch (err) {
        showToast("Failed to load profile", "error");
        navigate("/creator");
      } finally {
        setLoading(false);
      }
    };
    fetchProfile();
  }, [navigate]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setProfile(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await creatorApi.updateProfile(profile);
      showToast("Settings saved", "success");
      setTimeout(() => navigate("/creator"), 1500);
    } catch (err) {
      showToast("Failed to save settings", "error");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className={styles.container}><div className={styles.card}>Loading settings...</div></div>;
  }

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <h1>Creator settings</h1>
        <p className={styles.subtitle}>Manage your profile and payout preferences.</p>

        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.field}>
            <label>Display name</label>
            <input
              type="text"
              name="display_name"
              value={profile.display_name}
              onChange={handleChange}
              placeholder="How buyers see you"
            />
          </div>
          <div className={styles.field}>
            <label>Bio</label>
            <textarea
              name="bio"
              value={profile.bio}
              onChange={handleChange}
              placeholder="Tell buyers about yourself"
              rows="3"
            />
          </div>
          <div className={styles.divider} />
          <h3>Payout wallet</h3>
          <div className={styles.fieldGroup}>
            <div className={styles.field}>
              <label>Blockchain</label>
              <select name="custom_payout_blockchain" value={profile.custom_payout_blockchain} onChange={handleChange}>
                <option value="TRX">Tron (TRX) – lowest fees</option>
                <option value="ETH">Ethereum (ETH)</option>
                <option value="BTC">Bitcoin (BTC)</option>
                <option value="BASE">Base</option>
                <option value="POL">Polygon</option>
              </select>
            </div>
            <div className={styles.field}>
              <label>Currency</label>
              <select name="custom_payout_currency" value={profile.custom_payout_currency} onChange={handleChange}>
                <option value="USDT">USDT</option>
                <option value="USDC">USDC</option>
                <option value="BTC">BTC</option>
                <option value="ETH">ETH</option>
                <option value="TRX">TRX</option>
              </select>
            </div>
          </div>
          <div className={styles.field}>
            <label>Wallet address</label>
            <input
              type="text"
              name="custom_payout_wallet"
              value={profile.custom_payout_wallet}
              onChange={handleChange}
              placeholder="Leave empty to use your default CashSpace wallet"
            />
            <span className={styles.hint}>Your sales revenue will be sent to this wallet.</span>
          </div>
          <div className={styles.actions}>
            <button type="button" onClick={() => navigate("/creator")} className={styles.secondaryButton}>
              Cancel
            </button>
            <button type="submit" className={styles.primaryButton} disabled={saving}>
              {saving ? "Saving..." : "Save settings"}
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