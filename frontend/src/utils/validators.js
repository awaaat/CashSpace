// src/utils/validators.js
// Updated to support multi‑chain crypto address validation.

export const validateBTC = (addr) => {
  if (!addr) return "Wallet address is required";
  const ok = /^(1[a-km-zA-HJ-NP-Z1-9]{25,34}|3[a-km-zA-HJ-NP-Z1-9]{25,34}|bc1[a-z0-9]{39,59})$/.test(addr);
  if (!ok) return "Invalid BTC address (Legacy 1..., P2SH 3..., or Bech32 bc1...)";
  return null;
};

export const validateEmail = (email) => {
  if (!email) return "Email is required";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return "Invalid email address";
  return null;
};

export const validatePassword = (pw) => {
  if (!pw) return "Password is required";
  if (pw.length < 8) return "Password must be at least 8 characters";
  return null;
};

/**
 * Validate a crypto wallet address based on blockchain.
 * @param {string} blockchainCode - 'BTC', 'ETH', 'TRX', 'BASE', 'POL'
 * @param {string} address - The wallet address to validate
 * @returns {string|null} Error message or null if valid.
 */
export const validateCryptoAddress = (blockchainCode, address) => {
  if (!address) return "Wallet address is required";

  const blockchain = blockchainCode.toUpperCase();

  // Bitcoin
  if (blockchain === "BTC") {
    return validateBTC(address);
  }
  // Ethereum, Base, Polygon (EVM chains)
  else if (["ETH", "BASE", "POL"].includes(blockchain)) {
    const evmPattern = /^0x[a-fA-F0-9]{40}$/;
    if (!evmPattern.test(address)) {
      return `Invalid ${blockchainCode} address. Must be 0x-prefixed with 40 hex characters.`;
    }
  }
  // Tron
  else if (blockchain === "TRX") {
    const trxPattern = /^[A-Za-z0-9]{34}$/;
    if (!trxPattern.test(address)) {
      return "Invalid TRON address. Must be 34 alphanumeric characters (base58).";
    }
  }
  else {
    // Unknown blockchain – accept but optionally warn (no error for future expansion)
    return null;
  }
  return null;
};