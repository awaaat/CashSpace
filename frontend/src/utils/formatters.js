// src/utils/formatters.js

export const formatUSD = (val) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(val ?? 0);

export const formatBTC = (val) =>
  val ? `${parseFloat(val).toFixed(8)} ₿` : "—";

export const formatDate = (iso) =>
  iso
    ? new Date(iso).toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";

export const shortDate = (iso) =>
  iso
    ? new Date(iso).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
      })
    : "—";

export const truncateWallet = (addr, chars = 8) =>
  addr ? `${addr.slice(0, chars)}...${addr.slice(-6)}` : "—";

export const statusColor = (s) =>
  ({
    FILLED: "#22c55e",
    COMPLETED: "#22c55e",
    completed: "#22c55e",
    OPEN: "#3b82f6",
    "pending-approval": "#f59e0b",
    approved: "#8b5cf6",
    CANCELLED: "#6b7280",
    FAILED: "#ef4444",
    failed: "#ef4444",
    PENDING: "#6b7280",
    PARTIALLY_FILLED: "#f59e0b",
    NOT_INITIATED: "#374151",
  }[s] || "#6b7280");

/**
 * formatCryptoAmount — was missing, causing import crash in PaymentStatus.jsx
 * Formats a crypto amount with appropriate decimal places based on currency.
 */
export const formatCryptoAmount = (amount, currency) => {
  if (!amount) return "—";
  const stablecoins = ["USDT", "USDC"];
  const decimals = stablecoins.includes(currency) ? 2 : 8;
  const symbols = { BTC: "₿", ETH: "Ξ", USDT: "₮", USDC: "$", TRX: "TRX" };
  const symbol = symbols[currency] || "";
  return `${symbol}${Number(amount).toFixed(decimals)} ${currency}`;
};