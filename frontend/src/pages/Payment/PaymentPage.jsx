// src/pages/Payment/PaymentPage.jsx
import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { usePayments } from "../../hooks/usePayment";
import { paymentsApi } from "../../api/payments";
import { authApi } from "../../api/auth";
import { formatUSD, formatDate, statusColor, truncateWallet } from "../../utils/formatters";
import { validateCryptoAddress } from "../../utils/validators";
import styles from "./PaymentPage.module.css";

function formatCrypto(amount, currency) {
  if (!amount) return "—";
  const decimals = currency === "USDT" || currency === "USDC" ? 2 : 8;
  return `${Number(amount).toFixed(decimals)} ${currency}`;
}

// Custom Delete Confirmation Modal
function DeleteConfirmModal({ isOpen, onConfirm, onCancel, walletInfo }) {
  if (!isOpen) return null;
  return (
    <div className={styles.modalOverlay} onClick={onCancel}>
      <div className={styles.confirmModal} onClick={e => e.stopPropagation()}>
        <div className={styles.confirmHeader}>
          <h3>Delete Wallet</h3>
          <button className={styles.confirmClose} onClick={onCancel}>×</button>
        </div>
        <div className={styles.confirmBody}>
          <p>Are you sure you want to delete this wallet?</p>
          {walletInfo && (
            <div className={styles.confirmWalletInfo}>
              <span>{walletInfo.currency_code} on {walletInfo.blockchain_code}</span>
              <span className={styles.mono}>{truncateWallet(walletInfo.wallet_address)}</span>
            </div>
          )}
          <p className={styles.confirmWarning}>This action cannot be undone.</p>
        </div>
        <div className={styles.confirmFooter}>
          <button className={styles.confirmCancel} onClick={onCancel}>Cancel</button>
          <button className={styles.confirmDelete} onClick={onConfirm}>Delete</button>
        </div>
      </div>
    </div>
  );
}

export default function PaymentPage() {
  const navigate = useNavigate();
  const { payments, isLoading, fetchPayments, initiatePayment } = usePayments();

  // Payment modal state
  const [showModal, setShowModal] = useState(false);
  const [amount, setAmount] = useState("");
  const [selectedWalletId, setSelectedWalletId] = useState("");
  const [initiating, setInitiating] = useState(false);
  const [error, setError] = useState("");

  // Delete confirmation modal state
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [walletToDelete, setWalletToDelete] = useState(null);

  // Wallet management state
  const [wallets, setWallets] = useState([]);
  const [loadingWallets, setLoadingWallets] = useState(false);
  const [newWallet, setNewWallet] = useState({
    blockchain_code: "TRX",
    currency_code: "USDT",
    wallet_address: "",
    label: "",
    is_default: false,
  });
  const [walletMessage, setWalletMessage] = useState("");
  const [walletError, setWalletError] = useState("");

  const loadWallets = async () => {
    setLoadingWallets(true);
    try {
      const res = await authApi.getCryptoWallets();
      setWallets(Array.isArray(res.data?.results) ? res.data.results : []);
    } catch {
      setWallets([]);
    } finally {
      setLoadingWallets(false);
    }
  };

  useEffect(() => {
    loadWallets();
    fetchPayments();
  }, []);

  const handleAddWallet = async (e) => {
    e.preventDefault();
    const validationError = validateCryptoAddress(newWallet.blockchain_code, newWallet.wallet_address);
    if (validationError) {
      setWalletError(validationError);
      setWalletMessage("");
      return;
    }
    setWalletError("");
    setWalletMessage("");
    try {
      await authApi.addCryptoWallet(newWallet);
      await loadWallets();
      setNewWallet({
        blockchain_code: "TRX",
        currency_code: "USDT",
        wallet_address: "",
        label: "",
        is_default: false,
      });
      setWalletMessage("Wallet added successfully");
      setTimeout(() => setWalletMessage(""), 3000);
    } catch (err) {
      setWalletError(err.response?.data?.detail || "Failed to add wallet");
      setTimeout(() => setWalletError(""), 3000);
    }
  };

  const handleSetDefaultWallet = async (walletId) => {
    try {
      await authApi.setDefaultWallet(walletId);
      await loadWallets();
      setWalletMessage("Default wallet updated");
      setTimeout(() => setWalletMessage(""), 3000);
    } catch {
      setWalletError("Failed to set default wallet");
      setTimeout(() => setWalletError(""), 3000);
    }
  };

  const handleDeleteWallet = async () => {
    if (!walletToDelete) return;
    try {
      await authApi.deleteCryptoWallet(walletToDelete.id);
      await loadWallets();
      if (selectedWalletId === walletToDelete.id) setSelectedWalletId("");
      setWalletMessage("Wallet deleted");
      setTimeout(() => setWalletMessage(""), 3000);
    } catch {
      setWalletError("Failed to delete wallet");
      setTimeout(() => setWalletError(""), 3000);
    } finally {
      setDeleteModalOpen(false);
      setWalletToDelete(null);
    }
  };

  const handleInitiate = async (e) => {
    e.preventDefault();
    const amt = parseFloat(amount);
    if (isNaN(amt) || amt < 10 || amt > 10000) {
      setError("Amount must be between $10 and $10,000");
      return;
    }
    if (!selectedWalletId) {
      setError("Please select a wallet to receive the payout.");
      return;
    }
    setInitiating(true);
    setError("");
    try {
      const data = await initiatePayment(amt, selectedWalletId);
      if (data.payram_payment_url) {
        window.location.href = data.payram_payment_url;
      } else {
        setShowModal(false);
        setAmount("");
        setSelectedWalletId("");
      }
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to initiate payment");
    } finally {
      setInitiating(false);
    }
  };

  const selectedWallet = wallets.find(w => w.id === selectedWalletId);

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <button className={styles.backButton} onClick={() => navigate("/dashboard")}>
            ← Back to Dashboard
          </button>
          <h1 className={styles.title}>Buy Crypto</h1>
        </div>
        <button className={styles.primaryButton} onClick={() => setShowModal(true)}>
          + New Payment
        </button>
      </div>

      {/* Wallet Management Section */}
      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>Your Wallets</h2>
          <p className={styles.sectionDesc}>Manage where you receive crypto payouts.</p>
        </div>

        {/* Wallet Table */}
        <div className={styles.tableWrapper}>
          <table className={styles.walletTable}>
            <thead>
              <tr>
                <th>Blockchain</th><th>Currency</th><th>Address</th><th>Label</th><th>Default</th><th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loadingWallets ? (
                <tr><td colSpan="6" className={styles.loadingCell}>Loading wallets...</td></tr>
              ) : wallets.length === 0 ? (
                <tr><td colSpan="6" className={styles.emptyCell}>No wallets added yet. Add one below.</td></tr>
              ) : (
                wallets.map(w => (
                  <tr key={w.id}>
                    <td>{w.blockchain_code}</td>
                    <td>{w.currency_code}</td>
                    <td className={styles.mono}>{truncateWallet(w.wallet_address)}</td>
                    <td>{w.label || "—"}</td>
                    <td>{w.is_default ? <span className={styles.defaultBadge}>Default</span> : "—"}</td>
                    <td className={styles.actionsCell}>
                      {!w.is_default && (
                        <button className={styles.smallBtn} onClick={() => handleSetDefaultWallet(w.id)}>
                          Set default
                        </button>
                      )}
                      <button
                        className={`${styles.smallBtn} ${styles.dangerBtn}`}
                        onClick={() => {
                          setWalletToDelete(w);
                          setDeleteModalOpen(true);
                        }}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Add Wallet Form */}
        <div className={styles.addWalletCard}>
          <h3 className={styles.formTitle}>Add new wallet</h3>
          <form onSubmit={handleAddWallet} className={styles.form}>
            <div className={styles.formRow}>
              <div className={styles.formField}>
                <label className={styles.label}>Blockchain</label>
                <select className={styles.select} value={newWallet.blockchain_code} onChange={e => setNewWallet({...newWallet, blockchain_code: e.target.value})}>
                  <option value="BTC">Bitcoin (BTC)</option>
                  <option value="ETH">Ethereum (ETH)</option>
                  <option value="TRX">Tron (TRX)</option>
                  <option value="BASE">Base (BASE)</option>
                  <option value="POL">Polygon (POL)</option>
                </select>
              </div>
              <div className={styles.formField}>
                <label className={styles.label}>Currency</label>
                <select className={styles.select} value={newWallet.currency_code} onChange={e => setNewWallet({...newWallet, currency_code: e.target.value})}>
                  <option value="USDT">USDT</option>
                  <option value="USDC">USDC</option>
                  <option value="BTC">BTC</option>
                  <option value="ETH">ETH</option>
                  <option value="TRX">TRX</option>
                </select>
              </div>
            </div>
            <div className={styles.formField}>
              <label className={styles.label}>Wallet address</label>
              <input className={styles.input} value={newWallet.wallet_address} onChange={e => setNewWallet({...newWallet, wallet_address: e.target.value})} placeholder="Enter wallet address" required />
            </div>
            <div className={styles.formField}>
              <label className={styles.label}>Label (optional)</label>
              <input className={styles.input} value={newWallet.label} onChange={e => setNewWallet({...newWallet, label: e.target.value})} placeholder="e.g., My Trust Wallet" />
            </div>
            <div className={styles.checkboxField}>
              <input type="checkbox" id="is_default" checked={newWallet.is_default} onChange={e => setNewWallet({...newWallet, is_default: e.target.checked})} />
              <label htmlFor="is_default">Set as default for this blockchain/currency</label>
            </div>
            {walletMessage && <div className={styles.successMessage}>{walletMessage}</div>}
            {walletError && <div className={styles.errorMessage}>{walletError}</div>}
            <button type="submit" className={styles.submitBtn}>Add Wallet</button>
          </form>
        </div>
      </div>

      {/* Transaction History */}
      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>Transaction History</h2>
          <p className={styles.sectionDesc}>All your crypto purchases.</p>
        </div>
        {isLoading ? (
          <div className={styles.loading}><div className={styles.spinner} /></div>
        ) : (
          <div className={styles.tableWrapper}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Reference</th><th>Amount (USD)</th><th>Fee (30%)</th><th>You receive</th><th>Blockchain</th><th>Status</th><th>Date</th>
                </tr>
              </thead>
              <tbody>
                {payments.map(p => (
                  <tr key={p.id} onClick={() => navigate(`/payment/${p.id}`)} className={styles.row}>
                    <td className={styles.mono}>{p.payram_reference_id?.slice(0,12) || p.id.slice(0,12)}...</td>
                    <td className={styles.bold}>{formatUSD(p.amount_usd)}</td>
                    <td className={styles.muted}>{formatUSD(p.commission_usd)}</td>
                    <td className={styles.gold}>{formatCrypto(p.payout_crypto_amount, p.currency_code)}</td>
                    <td className={styles.mono}>{p.blockchain_code || "—"}</td>
                    <td><span className={styles.badge} style={{ background: `${statusColor(p.status)}22`, color: statusColor(p.status) }}>{p.status}</span></td>
                    <td className={styles.muted}>{formatDate(p.created_at)}</td>
                  </tr>
                ))}
                {payments.length === 0 && (
                  <tr><td colSpan="7" className={styles.emptyCell}>No transactions yet. Click "New Payment" to buy crypto.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Payment Modal */}
      {showModal && (
        <div className={styles.modalOverlay} onClick={() => setShowModal(false)}>
          <div className={styles.modal} onClick={e => e.stopPropagation()}>
            <div className={styles.modalHeader}>
              <h3>Buy Crypto</h3>
              <button className={styles.modalClose} onClick={() => setShowModal(false)}>×</button>
            </div>
            <div className={styles.modalBody}>
              <form onSubmit={handleInitiate} className={styles.modalForm}>
                <div className={styles.formField}>
                  <label className={styles.label}>Amount (USD)</label>
                  <input type="number" className={styles.input} min="10" max="10000" step="0.01" value={amount} onChange={e => setAmount(e.target.value)} placeholder="100.00" required autoFocus />
                </div>
                <div className={styles.formField}>
                  <label className={styles.label}>Receive to wallet</label>
                  {loadingWallets ? (
                    <div className={styles.spinnerSmall} />
                  ) : wallets.length === 0 ? (
                    <div className={styles.warningMessage}>No wallets found. Please add a wallet first.</div>
                  ) : (
                    <select className={styles.select} value={selectedWalletId} onChange={e => setSelectedWalletId(e.target.value)} required>
                      <option value="">Select a wallet</option>
                      {wallets.map(w => (
                        <option key={w.id} value={w.id}>{w.currency_code} on {w.blockchain_code} {w.is_default ? "(default)" : ""} — {truncateWallet(w.wallet_address)}</option>
                      ))}
                    </select>
                  )}
                </div>
                {amount && parseFloat(amount) >= 10 && selectedWallet && (
                  <div className={styles.breakdown}>
                    <div className={styles.breakRow}><span>You pay</span><span>{formatUSD(amount)}</span></div>
                    <div className={styles.breakRow}><span>Platform fee (30%)</span><span className={styles.fee}>−{formatUSD(parseFloat(amount)*0.3)}</span></div>
                    <div className={`${styles.breakRow} ${styles.total}`}><span>Crypto value sent (USD equiv)</span><span className={styles.gold}>{formatUSD(parseFloat(amount)*0.7)}</span></div>
                    <div className={styles.breakRow}><span>≈ in {selectedWallet.currency_code}</span><span className={styles.gold}>{formatCrypto(parseFloat(amount)*0.7, selectedWallet.currency_code)}</span></div>
                  </div>
                )}
                {error && <div className={styles.errorMessage}>{error}</div>}
                <button type="submit" className={styles.primaryButton} disabled={initiating || wallets.length === 0}>
                  {initiating ? <div className={styles.spinnerSmall} /> : "Proceed to checkout →"}
                </button>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Custom Delete Confirmation Modal */}
      <DeleteConfirmModal
        isOpen={deleteModalOpen}
        onConfirm={handleDeleteWallet}
        onCancel={() => {
          setDeleteModalOpen(false);
          setWalletToDelete(null);
        }}
        walletInfo={walletToDelete}
      />
    </div>
  );
}