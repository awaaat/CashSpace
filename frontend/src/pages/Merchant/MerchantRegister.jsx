import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import { merchantApi } from "../../api/merchant";
import styles from "./MerchantRegister.module.css";

export default function MerchantRegister() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    business_name: "",
    description: "",
    logo_url: "",
    settlement_blockchain: "TRX",
    settlement_currency: "USDT",
    settlement_wallet_address: "",
    webhook_url: "",
    webhook_secret: "",
  });

  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await merchantApi.register(form);
      navigate("/merchant");
    } catch (err) {
      const data = err.response?.data;
      if (data?.detail) {
        setError(data.detail);
      } else if (typeof data === "object") {
        const firstError = Object.values(data)[0]?.[0];
        setError(firstError || "Registration failed. Please check your inputs.");
      } else {
        setError("Registration failed. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <div className={styles.header}>
          <button className={styles.backButton} onClick={() => navigate("/dashboard")}>
            ← Back to Dashboard
          </button>
          <h1 className={styles.title}>Become a Merchant</h1>
        </div>
        <p className={styles.subtitle}>
          Accept payments from customers worldwide. Get settled in crypto automatically.
        </p>

        <form onSubmit={handleSubmit} className={styles.form}>
          {/* Business name */}
          <div className={styles.field}>
            <label>Business name *</label>
            <input
              name="business_name"
              value={form.business_name}
              onChange={handleChange}
              placeholder="e.g., Forex Academy Pro"
              required
            />
          </div>

          {/* Description */}
          <div className={styles.field}>
            <label>Description (optional)</label>
            <textarea
              name="description"
              value={form.description}
              onChange={handleChange}
              rows="3"
              placeholder="Tell your customers what you offer"
            />
          </div>

          {/* Logo URL */}
          <div className={styles.field}>
            <label>Logo URL (optional)</label>
            <input
              name="logo_url"
              value={form.logo_url}
              onChange={handleChange}
              placeholder="https://your-site.com/logo.png"
            />
          </div>

          {/* Blockchain & Currency */}
          <div className={styles.row}>
            <div className={styles.field}>
              <label>Settlement blockchain</label>
              <select
                name="settlement_blockchain"
                value={form.settlement_blockchain}
                onChange={handleChange}
              >
                <option value="TRX">Tron (TRX) – lowest fees</option>
                <option value="ETH">Ethereum (ETH)</option>
                <option value="BTC">Bitcoin (BTC)</option>
                <option value="BASE">Base</option>
                <option value="POL">Polygon</option>
              </select>
            </div>
            <div className={styles.field}>
              <label>Settlement currency</label>
              <select
                name="settlement_currency"
                value={form.settlement_currency}
                onChange={handleChange}
              >
                <option value="USDT">USDT</option>
                <option value="USDC">USDC</option>
                <option value="BTC">BTC</option>
                <option value="ETH">ETH</option>
                <option value="TRX">TRX</option>
              </select>
            </div>
          </div>

          {/* Wallet address */}
          <div className={styles.field}>
            <label>Settlement wallet address</label>
            <input
              name="settlement_wallet_address"
              value={form.settlement_wallet_address}
              onChange={handleChange}
              placeholder="Your crypto wallet address (leave empty to use your default wallet)"
            />
            <span className={styles.hint}>
              If left empty, your default CashSpace wallet will be used.
            </span>
          </div>

          {/* Webhook (advanced) */}
          <div className={styles.field}>
            <label>Webhook URL (optional)</label>
            <input
              name="webhook_url"
              value={form.webhook_url}
              onChange={handleChange}
              placeholder="https://your-server.com/webhook"
            />
          </div>

          <div className={styles.field}>
            <label>Webhook secret (optional)</label>
            <input
              name="webhook_secret"
              type="password"
              value={form.webhook_secret}
              onChange={handleChange}
              placeholder="HMAC signing secret"
            />
          </div>

          {error && <div className={styles.error}>{error}</div>}

          <button type="submit" className={styles.submitBtn} disabled={loading}>
            {loading ? <span className={styles.spinner} /> : "Create merchant account →"}
          </button>
        </form>

        <div className={styles.infoBox}>
          <p>💡 What happens next?</p>
          <ul>
            <li>Your merchant account will be reviewed (usually within 24 hours).</li>
            <li>Once approved, you can create products and start accepting payments.</li>
            <li>Your customers pay in local fiat – you receive crypto settlement automatically.</li>
          </ul>
        </div>
      </div>
    </div>
  );
}