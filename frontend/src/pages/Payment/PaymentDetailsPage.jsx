import React, { useState, useEffect, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { paymentsApi } from "../../api/payments";
import { formatUSD, formatDate, statusColor, truncateWallet } from "../../utils/formatters";
import styles from "./PaymentDetailsPage.module.css";

function formatCrypto(amount, currency) {
  if (!amount) return "—";
  const decimals = currency === "USDT" || currency === "USDC" ? 2 : 8;
  return `${Number(amount).toFixed(decimals)} ${currency}`;
}

function StatusBadge({ value }) {
  return (
    <span
      className={styles.badge}
      style={{ background: `${statusColor(value)}22`, color: statusColor(value) }}
    >
      {value}
    </span>
  );
}

function DetailRow({ label, value, mono, gold, bold }) {
  return (
    <div className={styles.detailRow}>
      <span className={styles.detailRowLabel}>{label}</span>
      <span
        className={[
          styles.detailRowValue,
          mono ? styles.mono : "",
          gold ? styles.gold : "",
          bold ? styles.bold : "",
        ]
          .filter(Boolean)
          .join(" ")}
      >
        {value ?? "—"}
      </span>
    </div>
  );
}

const TERMINAL_PAYMENT = ["FILLED", "CANCELLED", "FAILED"];
const TERMINAL_PAYOUT  = ["COMPLETED", "FAILED", "CANCELLED", "NOT_INITIATED"];
const POLL_INTERVAL = 5000;

export default function PaymentDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [payment, setPayment] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState("");
  const [polling, setPolling] = useState(false);
  const pollRef = useRef(null);

  const fetchDetail = async () => {
    try {
      const res = await paymentsApi.detail(id);
      setPayment(res.data);
      return res.data;
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to load payment.");
      return null;
    } finally {
      setLoading(false);
    }
  };

  const isFullyTerminal = (p) =>
    TERMINAL_PAYMENT.includes(p?.status) &&
    TERMINAL_PAYOUT.includes(p?.payout_status);

  const pollStatus = async () => {
    try {
      const res = await paymentsApi.status(id);
      setPayment(prev => prev ? { ...prev, ...res.data } : res.data);
      if (isFullyTerminal(res.data)) {
        clearInterval(pollRef.current);
        setPolling(false);
        await fetchDetail();
      }
    } catch {
      // silent — retry next tick
    }
  };

  useEffect(() => {
    fetchDetail().then(data => {
      if (!data) return;
      if (!isFullyTerminal(data)) {
        setPolling(true);
        pollRef.current = setInterval(pollStatus, POLL_INTERVAL);
      }
    });
    return () => clearInterval(pollRef.current);
  }, [id]);

  if (loading) {
    return (
      <div className={styles.detailPage}>
        <div className={styles.loading}><div className={styles.spinner} /></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.detailPage}>
        <button className={styles.backButton} onClick={() => navigate("/buy")}>← Back</button>
        <div className={styles.errorMessage} style={{ marginTop: "1rem" }}>{error}</div>
      </div>
    );
  }

  if (!payment) return null;

  const commissionRate = payment.commission_rate
    ? `${(parseFloat(payment.commission_rate) * 100).toFixed(0)}%`
    : "30%";

  return (
    <div className={styles.detailPage}>

      {/* ── Header ── */}
      <div className={styles.header} style={{ marginBottom: "1.25rem" }}>
        <div className={styles.headerLeft}>
          <button className={styles.backButton} onClick={() => navigate("/buy")}>
            ← Back
          </button>
          <h1 className={styles.title}>Payment Detail</h1>
        </div>
        {payment.payram_payment_url && !isFullyTerminal(payment) && (
          <a
            href={payment.payram_payment_url}
            target="_blank"
            rel="noopener noreferrer"
            className={styles.checkoutLink}
          >
            Open checkout →
          </a>
        )}
      </div>

      {/* ── Polling banner ── */}
      {polling && (
        <div className={styles.pollingBar}>
          <div className={styles.spinnerSmall} />
          Waiting for payment confirmation — refreshing automatically…
        </div>
      )}

      {/* ── Status card ── */}
      <div className={styles.detailCard}>
        <div className={styles.detailCardHeader}>
          <p className={styles.detailCardTitle}>Status</p>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
            <StatusBadge value={payment.status} />
            {payment.payout_status && (
              <span style={{ fontSize: "0.75rem", color: "#6b7280" }}>
                Payout: <StatusBadge value={payment.payout_status} />
              </span>
            )}
          </div>
        </div>
        <div className={styles.detailMetaGrid}>
          <div className={styles.detailMetaCell}>
            <div className={styles.detailMetaCellLabel}>Reference</div>
            <div className={styles.detailMetaCellValue}>
              {payment.payram_reference_id || payment.id}
            </div>
          </div>
          <div className={styles.detailMetaCell}>
            <div className={styles.detailMetaCellLabel}>Created</div>
            <div className={styles.detailMetaCellValuePlain}>{formatDate(payment.created_at)}</div>
          </div>
          <div className={styles.detailMetaCell}>
            <div className={styles.detailMetaCellLabel}>Last updated</div>
            <div className={styles.detailMetaCellValuePlain}>{formatDate(payment.updated_at)}</div>
          </div>
          <div className={styles.detailMetaCell}>
            <div className={styles.detailMetaCellLabel}>Payment method</div>
            <div className={styles.detailMetaCellValuePlain}>
              {payment.payment_method || "Card / Crypto"}
            </div>
          </div>
        </div>
      </div>

      {/* ── Financials card ── */}
      <div className={styles.detailCard}>
        <div className={styles.detailCardHeader}>
          <p className={styles.detailCardTitle}>Financials</p>
        </div>
        <DetailRow label="You paid"                    value={formatUSD(payment.amount_usd)} bold />
        <DetailRow label={`Platform fee (${commissionRate})`} value={payment.commission_usd ? `−${formatUSD(payment.commission_usd)}` : "—"} />
        <div className={styles.detailDivider} />
        <DetailRow label="Payout value (USD equiv.)"   value={formatUSD(payment.payout_usd_equivalent)} bold gold />
        <DetailRow label="Crypto amount"               value={formatCrypto(payment.payout_crypto_amount, payment.currency_code)} gold />
        {payment.exchange_rate_usd_to_crypto && (
          <DetailRow
            label={`Exchange rate (USD → ${payment.currency_code})`}
            value={`1 USD = ${parseFloat(payment.exchange_rate_usd_to_crypto).toFixed(6)} ${payment.currency_code}`}
          />
        )}
      </div>

      {/* ── Destination card ── */}
      <div className={styles.detailCard}>
        <div className={styles.detailCardHeader}>
          <p className={styles.detailCardTitle}>Destination</p>
        </div>
        <DetailRow label="Blockchain" value={payment.blockchain_display || payment.blockchain_code} />
        <DetailRow label="Currency"   value={payment.currency_display  || payment.currency_code} />
        <DetailRow label="Wallet address" value={payment.destination_wallet} mono />
      </div>

      {/* ── Payout tracking card ── */}
      <div className={styles.detailCard}>
        <div className={styles.detailCardHeader}>
          <p className={styles.detailCardTitle}>Payout tracking</p>
          {payment.payout_status && <StatusBadge value={payment.payout_status} />}
        </div>
        <DetailRow
          label="Payout ID"
          value={payment.payram_payout_id || "Pending"}
          mono={!!payment.payram_payout_id}
        />
        <DetailRow
          label="Initiated at"
          value={payment.payout_initiated_at ? formatDate(payment.payout_initiated_at) : "Pending"}
        />
        <DetailRow
          label="Completed at"
          value={payment.payout_completed_at ? formatDate(payment.payout_completed_at) : "Pending"}
        />
        {payment.payout_error   && <DetailRow label="Payout error" value={payment.payout_error} />}
        {payment.error_message  && <DetailRow label="Error"        value={payment.error_message} />}
      </div>

      {/* ── Debug info (only when relevant) ── */}
      {(payment.webhook_count > 0 || payment.last_webhook_at || payment.notes) && (
        <div className={styles.detailCard}>
          <div className={styles.detailCardHeader}>
            <p className={styles.detailCardTitle}>Debug info</p>
          </div>
          {payment.last_webhook_at  && <DetailRow label="Last webhook"       value={formatDate(payment.last_webhook_at)} />}
          {payment.webhook_count > 0 && <DetailRow label="Webhook events"    value={payment.webhook_count} />}
          {payment.payram_raw_status && <DetailRow label="Raw PayRam status" value={payment.payram_raw_status} mono />}
          {payment.notes             && <DetailRow label="Notes"             value={payment.notes} />}
        </div>
      )}

    </div>
  );
}