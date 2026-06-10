// frontend/src/pages/Creator/CreatorRegister.jsx
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import { creatorApi } from "../../api/creator";
import styles from "./CreatorRegister.module.css";

export default function CreatorRegister() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [displayName, setDisplayName] = useState(user?.first_name || "");
  const [bio, setBio] = useState("");
  const [payoutWallet, setPayoutWallet] = useState("");
  const [payoutBlockchain, setPayoutBlockchain] = useState("TRX");
  const [payoutCurrency, setPayoutCurrency] = useState("USDT");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      // First, get or create profile via getProfile (auto-creates if missing)
      const profileRes = await creatorApi.getProfile();
      if (!profileRes.data) {
        throw new Error("Failed to create profile");
      }
      // Update profile with user's preferences
      await creatorApi.updateProfile({
        display_name: displayName,
        bio: bio,
        custom_payout_wallet: payoutWallet,
        custom_payout_blockchain: payoutBlockchain,
        custom_payout_currency: payoutCurrency,
      });
      navigate("/creator");
    } catch (err) {
      console.error(err);
      setError("Could not activate creator account. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <h1>Activate creator account</h1>
        <p className={styles.subtitle}>
          As a creator, you can sell access to any link, file, or hidden content.
          No approval needed – just set a price and share your link.
        </p>

        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.field}>
            <label>Display name (optional)</label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="How you want to be seen"
            />
          </div>

          <div className={styles.field}>
            <label>Bio (optional)</label>
            <textarea
              value={bio}
              onChange={(e) => setBio(e.target.value)}
              placeholder="Tell buyers about yourself"
              rows="3"
            />
          </div>

          <div className={styles.fieldGroup}>
            <div className={styles.field}>
              <label>Payout blockchain</label>
              <select value={payoutBlockchain} onChange={(e) => setPayoutBlockchain(e.target.value)}>
                <option value="TRX">Tron (TRX) – lowest fees</option>
                <option value="ETH">Ethereum (ETH)</option>
                <option value="BTC">Bitcoin (BTC)</option>
                <option value="BASE">Base</option>
                <option value="POL">Polygon</option>
              </select>
            </div>
            <div className={styles.field}>
              <label>Payout currency</label>
              <select value={payoutCurrency} onChange={(e) => setPayoutCurrency(e.target.value)}>
                <option value="USDT">USDT</option>
                <option value="USDC">USDC</option>
                <option value="BTC">BTC</option>
                <option value="ETH">ETH</option>
                <option value="TRX">TRX</option>
              </select>
            </div>
          </div>

          <div className={styles.field}>
            <label>Wallet address (optional)</label>
            <input
              type="text"
              value={payoutWallet}
              onChange={(e) => setPayoutWallet(e.target.value)}
              placeholder="Leave empty to use your default CashSpace wallet"
            />
            <span className={styles.hint}>
              Your sales revenue will be sent to this wallet. You can change it later.
            </span>
          </div>

          {error && <div className={styles.error}>{error}</div>}

          <button type="submit" className={styles.button} disabled={loading}>
            {loading ? "Activating..." : "Activate creator account"}
          </button>
        </form>

        <div className={styles.info}>
          <p>When you sell an asset:</p>
          <ul>
            <li>Buyers pay using card or crypto.</li>
            <li>CashSpace takes a small commission (default 30%).</li>
            <li>The net amount is sent to your payout wallet.</li>
            <li>You can create unlimited payable links.</li>
          </ul>
        </div>
      </div>
    </div>
  );
}