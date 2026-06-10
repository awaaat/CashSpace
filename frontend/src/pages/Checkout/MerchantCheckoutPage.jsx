/**
 * MerchantCheckoutPage.jsx
 * ========================
 * Public checkout page — no auth required.
 * Route: /pay/:merchantSlug/:productSlug/
 *
 * Architecture (PayRam hidden from buyer):
 *   Step 1 — DETAILS    : Show product info, collect buyer identity
 *   Step 2 — PAYMENT    : Buyer chooses payment method (Card or Crypto)
 *                         Card  → PayRam URL opens in a fullscreen modal iframe
 *                                 (buyer stays on cashspace.com domain)
 *                         Crypto → We show wallet address + QR code ourselves
 *                                  (PayRam's address, our branded UI)
 *   Step 3 — CONFIRMING : We poll our own backend for payment status
 *   Step 4 — SUCCESS    : Branded success screen
 *
 * Test mode:
 *   If URL contains ?mode=test OR merchant is in test mode,
 *   the checkout shows a yellow TEST MODE banner and uses
 *   our backend's test-sale endpoint instead of real PayRam.
 *
 * Environment detection is handled by the backend — the frontend just
 * reads `is_test_mode` from the product/merchant response.
 */

import React, {
  useState, useEffect, useCallback, useRef, useMemo
} from "react";
import { useParams, useSearchParams } from "react-router-dom";
import api from "../../api/axios";
import styles from "./MerchantCheckoutPage.module.css";

// ─── Constants ────────────────────────────────────────────────────────────────

const POLL_INTERVAL_MS = 3000;
const POLL_MAX_ATTEMPTS = 60; // 3 min max polling

// Steps
const STEP = {
  LOADING:     "loading",
  ERROR:       "error",
  SOLD_OUT:    "sold_out",
  DETAILS:     "details",     // product info + identity form
  PAYMENT:     "payment",     // choose method + pay
  CONFIRMING:  "confirming",  // polling status
  SUCCESS:     "success",
};

// ─── Utilities ────────────────────────────────────────────────────────────────

const fmt = (n) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(n ?? 0);

function copyToClipboard(text) {
  if (navigator.clipboard) return navigator.clipboard.writeText(text);
  const el = document.createElement("textarea");
  el.value = text;
  document.body.appendChild(el);
  el.select();
  document.execCommand("copy");
  document.body.removeChild(el);
  return Promise.resolve();
}

// Minimal QR code via a free, privacy-safe API (no tracking, open source)
// We use api.qrserver.com — it's a public API, acceptable for MVP.
// For production: replace with a self-hosted qrcodegen library.
function QRCode({ value, size = 180 }) {
  if (!value) return null;
  const src = `https://api.qrserver.com/v1/create-qr-code/?size=${size}x${size}&data=${encodeURIComponent(value)}&margin=10&bgcolor=ffffff&color=000000`;
  return (
    <img
      src={src}
      alt="Payment QR code"
      className={styles.qrImage}
      width={size}
      height={size}
    />
  );
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function TestModeBanner() {
  return (
    <div className={styles.testBanner}>
      <span className={styles.testBannerDot} />
      TEST MODE — No real payments are processed
    </div>
  );
}

function MerchantBrand({ merchant, product }) {
  return (
    <div className={styles.brand}>
      {merchant.logo_url && (
        <img
          src={merchant.logo_url}
          alt={merchant.business_name}
          className={styles.brandLogo}
          onError={(e) => { e.target.style.display = "none"; }}
        />
      )}
      <div className={styles.brandText}>
        <div className={styles.brandName}>{merchant.business_name}</div>
        {merchant.description && (
          <div className={styles.brandDesc}>{merchant.description}</div>
        )}
      </div>
    </div>
  );
}

function ProductSummary({ product, amount }) {
  const price = amount ?? product.price_usd;
  const isPwyw = product.product_type === "donation";

  return (
    <div className={styles.productSummary}>
      <div className={styles.productSummaryName}>{product.name}</div>
      {product.description && (
        <div className={styles.productSummaryDesc}>{product.description}</div>
      )}
      <div className={styles.productSummaryPrice}>
        {isPwyw && !amount
          ? <span className={styles.pwywLabel}>Pay what you want</span>
          : <span className={styles.priceAmount}>{fmt(price)}</span>
        }
      </div>
    </div>
  );
}

function StepIndicator({ current }) {
  const steps = [
    { id: "details",    label: "Details" },
    { id: "payment",   label: "Payment" },
    { id: "confirming", label: "Confirm" },
  ];
  const activeIdx = steps.findIndex(s => s.id === current);

  return (
    <div className={styles.stepIndicator}>
      {steps.map((s, i) => (
        <React.Fragment key={s.id}>
          <div className={`${styles.stepDot} ${i <= activeIdx ? styles.stepDotActive : ""} ${i < activeIdx ? styles.stepDotDone : ""}`}>
            {i < activeIdx ? "✓" : i + 1}
          </div>
          {i < steps.length - 1 && (
            <div className={`${styles.stepLine} ${i < activeIdx ? styles.stepLineDone : ""}`} />
          )}
        </React.Fragment>
      ))}
    </div>
  );
}

// Identity form — collects buyer info based on product config
function IdentityForm({ product, form, onChange, errors }) {
  const set = (k) => (e) => onChange(k, e.target.value);

  return (
    <div className={styles.identityForm}>
      <div className={styles.formGroup}>
        <label className={styles.label}>Email address <span className={styles.required}>*</span></label>
        <input
          type="email"
          className={`${styles.input} ${errors.email ? styles.inputError : ""}`}
          value={form.email}
          onChange={set("email")}
          placeholder="you@example.com"
          autoComplete="email"
        />
        {errors.email && <span className={styles.fieldError}>{errors.email}</span>}
      </div>

      <div className={styles.formGroup}>
        <label className={styles.label}>Full name</label>
        <input
          type="text"
          className={styles.input}
          value={form.full_name}
          onChange={set("full_name")}
          placeholder="Jane Doe"
          autoComplete="name"
        />
      </div>

      {product.collect_telegram && (
        <div className={styles.formGroup}>
          <label className={styles.label}>
            Telegram username <span className={styles.required}>*</span>
          </label>
          <div className={styles.inputPrefix}>
            <span className={styles.prefix}>@</span>
            <input
              type="text"
              className={`${styles.input} ${styles.inputWithPrefix} ${errors.telegram_username ? styles.inputError : ""}`}
              value={form.telegram_username}
              onChange={set("telegram_username")}
              placeholder="yourusername"
            />
          </div>
          {errors.telegram_username && <span className={styles.fieldError}>{errors.telegram_username}</span>}
        </div>
      )}

      {product.collect_discord && (
        <div className={styles.formGroup}>
          <label className={styles.label}>
            Discord username <span className={styles.required}>*</span>
          </label>
          <input
            type="text"
            className={`${styles.input} ${errors.discord_username ? styles.inputError : ""}`}
            value={form.discord_username}
            onChange={set("discord_username")}
            placeholder="username or user#1234"
          />
          {errors.discord_username && <span className={styles.fieldError}>{errors.discord_username}</span>}
        </div>
      )}

      {product.collect_phone && (
        <div className={styles.formGroup}>
          <label className={styles.label}>
            Phone number <span className={styles.required}>*</span>
          </label>
          <input
            type="tel"
            className={`${styles.input} ${errors.phone_number ? styles.inputError : ""}`}
            value={form.phone_number}
            onChange={set("phone_number")}
            placeholder="+1 555 000 0000"
            autoComplete="tel"
          />
          {errors.phone_number && <span className={styles.fieldError}>{errors.phone_number}</span>}
        </div>
      )}

      {product.collect_custom_field && (
        <div className={styles.formGroup}>
          <label className={styles.label}>
            {product.collect_custom_field} <span className={styles.required}>*</span>
          </label>
          <input
            type="text"
            className={`${styles.input} ${errors.custom_field_value ? styles.inputError : ""}`}
            value={form.custom_field_value}
            onChange={set("custom_field_value")}
          />
          {errors.custom_field_value && <span className={styles.fieldError}>{errors.custom_field_value}</span>}
        </div>
      )}

      {product.product_type === "donation" && (
        <div className={styles.formGroup}>
          <label className={styles.label}>
            Amount (USD) <span className={styles.required}>*</span>
          </label>
          <div className={styles.amountInput}>
            <span className={styles.currencySymbol}>$</span>
            <input
              type="number"
              className={`${styles.input} ${styles.inputWithPrefix} ${errors.amount_usd ? styles.inputError : ""}`}
              value={form.amount_usd}
              onChange={set("amount_usd")}
              min={product.min_price_usd || 10}
              step="0.01"
              placeholder={`Min $${product.min_price_usd || 10}`}
            />
          </div>
          {errors.amount_usd && <span className={styles.fieldError}>{errors.amount_usd}</span>}
        </div>
      )}
    </div>
  );
}

// Payment method selector
function PaymentMethodSelector({ selected, onSelect, isTestMode }) {
  return (
    <div className={styles.methodSelector}>
      <button
        type="button"
        className={`${styles.methodCard} ${selected === "card" ? styles.methodCardActive : ""}`}
        onClick={() => onSelect("card")}
      >
        <div className={styles.methodIcon}>💳</div>
        <div className={styles.methodInfo}>
          <div className={styles.methodName}>Card</div>
          <div className={styles.methodDesc}>Visa, Mastercard · Any currency</div>
        </div>
        {selected === "card" && <span className={styles.methodCheck}>✓</span>}
      </button>

      <button
        type="button"
        className={`${styles.methodCard} ${selected === "crypto" ? styles.methodCardActive : ""}`}
        onClick={() => onSelect("crypto")}
      >
        <div className={styles.methodIcon}>₿</div>
        <div className={styles.methodInfo}>
          <div className={styles.methodName}>Crypto</div>
          <div className={styles.methodDesc}>USDT, USDC, BTC, ETH · Instant</div>
        </div>
        {selected === "crypto" && <span className={styles.methodCheck}>✓</span>}
      </button>
    </div>
  );
}

// Card payment — PayRam URL in a branded modal iframe
// The buyer never sees the PayRam branding in the URL bar — they're still on cashspace.com
function CardPaymentModal({ payramUrl, onSuccess, onCancel, isTestMode }) {
  const [iframeLoaded, setIframeLoaded] = useState(false);

  // Poll our backend for status change while iframe is open
  // (PayRam will fire a webhook to our backend; we poll our backend)
  useEffect(() => {
    // The parent component's polling handles status — this is just the visual layer
  }, []);

  if (isTestMode) {
    return (
      <div className={styles.cardModal}>
        <div className={styles.cardModalHeader}>
          <span className={styles.cardModalTitle}>Complete Payment</span>
          <button className={styles.cardModalClose} onClick={onCancel}>×</button>
        </div>
        <div className={styles.testPaymentBox}>
          <div className={styles.testPaymentIcon}>🧪</div>
          <div className={styles.testPaymentTitle}>Test Mode Payment</div>
          <p className={styles.testPaymentDesc}>
            In test mode, no real payment is processed. Click below to simulate a successful payment.
          </p>
          <button className={styles.testPayBtn} onClick={onSuccess}>
            Simulate successful payment →
          </button>
          <button className={styles.testPayCancel} onClick={onCancel}>Cancel</button>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.cardModal}>
      <div className={styles.cardModalHeader}>
        <span className={styles.cardModalTitle}>Complete Payment</span>
        <button className={styles.cardModalClose} onClick={onCancel}>×</button>
      </div>
      <div className={styles.cardModalBody}>
        {!iframeLoaded && (
          <div className={styles.iframeLoader}>
            <div className={styles.spinner} />
            <span>Loading secure payment form…</span>
          </div>
        )}
        <iframe
          src={payramUrl}
          className={`${styles.paymentIframe} ${iframeLoaded ? styles.iframeVisible : ""}`}
          onLoad={() => setIframeLoaded(true)}
          title="Secure payment form"
          allow="payment"
          sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
        />
      </div>
      <div className={styles.cardModalFooter}>
        <span className={styles.secureNote}>🔒 Secured with 256-bit SSL encryption</span>
      </div>
    </div>
  );
}

// Crypto payment — fully our UI, PayRam is invisible
function CryptoPayment({ checkoutData, onCopied }) {
  const [copied, setCopied] = useState(false);
  const address = checkoutData?.destination_wallet;
  const amount = checkoutData?.amount_usd;
  const currency = checkoutData?.currency_code || "USDT";
  const blockchain = checkoutData?.blockchain_code || "TRX";

  const handleCopy = async () => {
    await copyToClipboard(address);
    setCopied(true);
    onCopied?.();
    setTimeout(() => setCopied(false), 2500);
  };

  return (
    <div className={styles.cryptoPayment}>
      <div className={styles.cryptoChain}>
        Send <strong>{fmt(amount)} worth of {currency}</strong> on the <strong>{blockchain}</strong> network
      </div>

      <div className={styles.qrWrapper}>
        <QRCode value={address} size={160} />
      </div>

      <div className={styles.addressBox}>
        <div className={styles.addressLabel}>Wallet address</div>
        <div className={styles.addressRow}>
          <code className={styles.address}>{address}</code>
          <button className={styles.copyBtn} onClick={handleCopy}>
            {copied ? "Copied ✓" : "Copy"}
          </button>
        </div>
      </div>

      <div className={styles.cryptoWarnings}>
        <div className={styles.cryptoWarning}>
          ⚠️ Only send <strong>{currency}</strong> on the <strong>{blockchain}</strong> network. Sending any other token will result in permanent loss.
        </div>
        <div className={styles.cryptoWarning}>
          Send the exact amount of <strong>{currency}</strong> equivalent to <strong>{fmt(amount)}</strong>.
        </div>
      </div>

      <div className={styles.confirming}>
        <div className={styles.confirmingDots}>
          <span /><span /><span />
        </div>
        Waiting for payment confirmation…
      </div>
    </div>
  );
}

// Confirming screen — polls backend
function ConfirmingScreen() {
  return (
    <div className={styles.confirmingScreen}>
      <div className={styles.confirmingSpinner} />
      <h3 className={styles.confirmingTitle}>Confirming your payment</h3>
      <p className={styles.confirmingDesc}>
        This usually takes a few seconds for card payments and 1–3 minutes for crypto.
        Please keep this page open.
      </p>
    </div>
  );
}

// Success screen
function SuccessScreen({ product, merchant, checkoutId, redirectUrl }) {
  useEffect(() => {
    if (redirectUrl) {
      const timer = setTimeout(() => {
        window.location.href = redirectUrl;
      }, 4000);
      return () => clearTimeout(timer);
    }
  }, [redirectUrl]);

  return (
    <div className={styles.successScreen}>
      <div className={styles.successIcon}>✓</div>
      <h2 className={styles.successTitle}>Payment confirmed</h2>
      <p className={styles.successDesc}>
        Thank you for your purchase of <strong>{product.name}</strong>.
        A confirmation has been sent to your email.
      </p>
      {redirectUrl && (
        <p className={styles.redirectNote}>
          Redirecting you in a few seconds…
        </p>
      )}
      <div className={styles.successRef}>
        Reference: <code>{checkoutId?.slice(0, 8).toUpperCase()}</code>
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function MerchantCheckoutPage() {
  const { merchantSlug, productSlug } = useParams();
  const [searchParams] = useSearchParams();
  const isTestModeParam = searchParams.get("mode") === "test";

  const [step, setStep] = useState(STEP.LOADING);
  const [merchant, setMerchant] = useState(null);
  const [product, setProduct] = useState(null);
  const [errorMsg, setErrorMsg] = useState("");
  const [isTestMode, setIsTestMode] = useState(isTestModeParam);

  // Identity form state
  const [form, setForm] = useState({
    email: "",
    full_name: "",
    telegram_username: "",
    discord_username: "",
    phone_number: "",
    custom_field_value: "",
    amount_usd: "",
  });
  const [fieldErrors, setFieldErrors] = useState({});

  // Payment state
  const [paymentMethod, setPaymentMethod] = useState("card");
  const [checkoutResponse, setCheckoutResponse] = useState(null); // from POST /checkout/
  const [submitting, setSubmitting] = useState(false);
  const [showCardModal, setShowCardModal] = useState(false);

  // Polling state
  const pollRef = useRef(null);
  const pollAttempts = useRef(0);

  // ── Load product on mount ──────────────────────────────────────────────────
  useEffect(() => {
    const load = async () => {
      try {
        const { data } = await api.get(`/pay/${merchantSlug}/${productSlug}/`);
        setMerchant({
          business_name: data.merchant_name,
          logo_url: data.merchant_logo,
          description: data.merchant_description,
          slug: merchantSlug,
        });
        setProduct(data);
        // Check test mode from product response
        if (data.is_test_mode) setIsTestMode(true);

        if (data.is_sold_out) {
          setStep(STEP.SOLD_OUT);
        } else {
          setStep(STEP.DETAILS);
        }
      } catch (err) {
        if (err.response?.status === 410) {
          setStep(STEP.SOLD_OUT);
        } else if (err.response?.status === 404) {
          setErrorMsg("This payment link is no longer active.");
          setStep(STEP.ERROR);
        } else {
          setErrorMsg("Something went wrong loading this page. Please try again.");
          setStep(STEP.ERROR);
        }
      }
    };
    load();
  }, [merchantSlug, productSlug]);

  // ── Cleanup polling on unmount ─────────────────────────────────────────────
  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  // ── Form field handler ────────────────────────────────────────────────────
  const handleFieldChange = useCallback((key, value) => {
    setForm(f => ({ ...f, [key]: value }));
    setFieldErrors(e => ({ ...e, [key]: "" }));
  }, []);

  // ── Client-side form validation ───────────────────────────────────────────
  const validateForm = useCallback(() => {
    const errs = {};
    if (!form.email || !/\S+@\S+\.\S+/.test(form.email)) {
      errs.email = "Valid email address is required.";
    }
    if (product.collect_telegram && !form.telegram_username) {
      errs.telegram_username = "Telegram username is required for this product.";
    }
    if (product.collect_discord && !form.discord_username) {
      errs.discord_username = "Discord username is required.";
    }
    if (product.collect_phone && !form.phone_number) {
      errs.phone_number = "Phone number is required.";
    }
    if (product.collect_custom_field && !form.custom_field_value) {
      errs.custom_field_value = `${product.collect_custom_field} is required.`;
    }
    if (product.product_type === "donation") {
      const amt = parseFloat(form.amount_usd);
      const min = parseFloat(product.min_price_usd || 10);
      if (!form.amount_usd || isNaN(amt) || amt < min) {
        errs.amount_usd = `Minimum amount is $${min}.`;
      }
    }
    setFieldErrors(errs);
    return Object.keys(errs).length === 0;
  }, [form, product]);

  // ── Submit identity form → go to payment step ─────────────────────────────
  const handleDetailsSubmit = useCallback((e) => {
    e.preventDefault();
    if (!validateForm()) return;
    setStep(STEP.PAYMENT);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [validateForm]);

  // ── Submit checkout → create PayRam session ───────────────────────────────
  const handlePayNow = useCallback(async () => {
    if (submitting) return;
    setSubmitting(true);

    try {
      const payload = {
        email: form.email,
        full_name: form.full_name,
        telegram_username: form.telegram_username,
        discord_username: form.discord_username,
        phone_number: form.phone_number,
        custom_field_value: form.custom_field_value,
      };
      if (product.product_type === "donation") {
        payload.amount_usd = parseFloat(form.amount_usd);
      }

      const endpoint = isTestMode
        ? `/pay/${merchantSlug}/${productSlug}/checkout/?mode=test`
        : `/pay/${merchantSlug}/${productSlug}/checkout/`;

      const { data } = await api.post(endpoint, payload);
      setCheckoutResponse(data);

      if (paymentMethod === "card") {
        setShowCardModal(true);
        // Start polling — card payment status comes via webhook to our backend
        startPolling(data.checkout_id);
      } else {
        // Crypto: show address UI + start polling
        startPolling(data.checkout_id);
      }
    } catch (err) {
      const detail = err.response?.data?.detail
        || Object.values(err.response?.data || {})[0]?.[0]
        || "Something went wrong. Please try again.";
      setErrorMsg(detail);
    } finally {
      setSubmitting(false);
    }
  }, [form, product, paymentMethod, merchantSlug, productSlug, isTestMode, submitting]);

  // ── Poll our backend for payment status ───────────────────────────────────
  const startPolling = useCallback((checkoutId) => {
    pollAttempts.current = 0;

    pollRef.current = setInterval(async () => {
      pollAttempts.current += 1;

      if (pollAttempts.current > POLL_MAX_ATTEMPTS) {
        clearInterval(pollRef.current);
        return;
      }

      try {
        const { data } = await api.get(
          `/pay/${merchantSlug}/${productSlug}/checkout/${checkoutId}/status/`
        );

        if (data.status === "completed") {
          clearInterval(pollRef.current);
          setShowCardModal(false);
          setStep(STEP.SUCCESS);
        } else if (data.status === "abandoned" || data.payment_status === "FAILED") {
          clearInterval(pollRef.current);
          setErrorMsg("Payment was not completed. Please try again.");
        }
        // Otherwise keep polling
      } catch {
        // Swallow poll errors — transient network issues
      }
    }, POLL_INTERVAL_MS);
  }, [merchantSlug, productSlug]);

  // ── Test mode simulate success ─────────────────────────────────────────────
  const handleTestSuccess = useCallback(async () => {
    if (!checkoutResponse) return;
    try {
      // Hit our test-complete endpoint to mark checkout as completed
      await api.post(
        `/pay/${merchantSlug}/${productSlug}/checkout/${checkoutResponse.checkout_id}/test-complete/`
      );
    } catch {
      // Continue to success screen regardless
    }
    clearInterval(pollRef.current);
    setShowCardModal(false);
    setStep(STEP.SUCCESS);
  }, [checkoutResponse, merchantSlug, productSlug]);

  // ── Derived values ─────────────────────────────────────────────────────────
  const displayAmount = useMemo(() => {
    if (product?.product_type === "donation" && form.amount_usd) {
      return parseFloat(form.amount_usd);
    }
    return product?.price_usd;
  }, [product, form.amount_usd]);

  const showProductSummary = step !== STEP.LOADING && step !== STEP.ERROR && product;

  // ─────────────────────────────────────────────────────────────────────────
  // RENDER
  // ─────────────────────────────────────────────────────────────────────────

  return (
    <div className={styles.page}>
      {isTestMode && <TestModeBanner />}

      <div className={styles.layout}>
        {/* Left panel — product info (desktop) */}
        <div className={styles.leftPanel}>
          {showProductSummary && (
            <>
              <MerchantBrand merchant={merchant} product={product} />
              <ProductSummary product={product} amount={displayAmount} />

              <div className={styles.trustItems}>
                <div className={styles.trustItem}>🔒 Secure checkout</div>
                <div className={styles.trustItem}>💬 Email confirmation</div>
                <div className={styles.trustItem}>⚡ Instant access</div>
              </div>
            </>
          )}
        </div>

        {/* Right panel — checkout flow */}
        <div className={styles.rightPanel}>
          {/* Step indicator */}
          {(step === STEP.DETAILS || step === STEP.PAYMENT || step === STEP.CONFIRMING) && (
            <StepIndicator current={step} />
          )}

          {/* Mobile: show product name */}
          {showProductSummary && (
            <div className={styles.mobileSummary}>
              <span className={styles.mobileMerchant}>{merchant?.business_name}</span>
              <span className={styles.mobileSep}>·</span>
              <span className={styles.mobileProduct}>{product?.name}</span>
              {displayAmount && (
                <span className={styles.mobilePrice}>{fmt(displayAmount)}</span>
              )}
            </div>
          )}

          {/* ── LOADING ── */}
          {step === STEP.LOADING && (
            <div className={styles.loadingBox}>
              <div className={styles.spinner} />
              <span>Loading checkout…</span>
            </div>
          )}

          {/* ── ERROR ── */}
          {step === STEP.ERROR && (
            <div className={styles.errorBox}>
              <div className={styles.errorIcon}>⚠</div>
              <h3 className={styles.errorTitle}>Unable to load checkout</h3>
              <p className={styles.errorDesc}>{errorMsg}</p>
            </div>
          )}

          {/* ── SOLD OUT ── */}
          {step === STEP.SOLD_OUT && (
            <div className={styles.soldOutBox}>
              <div className={styles.soldOutIcon}>🚫</div>
              <h3 className={styles.soldOutTitle}>Sold out</h3>
              <p className={styles.soldOutDesc}>
                This product is no longer available. Contact {merchant?.business_name || "the seller"} for more information.
              </p>
            </div>
          )}

          {/* ── STEP 1: DETAILS ── */}
          {step === STEP.DETAILS && product && (
            <form onSubmit={handleDetailsSubmit} className={styles.card} noValidate>
              <h2 className={styles.cardTitle}>Your details</h2>
              <p className={styles.cardSub}>
                Enter your information below. This is how the seller will reach you.
              </p>

              <IdentityForm
                product={product}
                form={form}
                onChange={handleFieldChange}
                errors={fieldErrors}
              />

              <button type="submit" className={styles.continueBtn}>
                Continue to payment →
              </button>

              <p className={styles.legalNote}>
                By continuing, you agree to the payment terms. Your information is only shared with {merchant?.business_name}.
              </p>
            </form>
          )}

          {/* ── STEP 2: PAYMENT ── */}
          {step === STEP.PAYMENT && product && !checkoutResponse && (
            <div className={styles.card}>
              <h2 className={styles.cardTitle}>Payment</h2>
              <p className={styles.cardSub}>
                Choose how you'd like to pay{displayAmount ? ` ${fmt(displayAmount)}` : ""}.
              </p>

              <PaymentMethodSelector
                selected={paymentMethod}
                onSelect={setPaymentMethod}
                isTestMode={isTestMode}
              />

              {errorMsg && (
                <div className={styles.inlineError}>{errorMsg}</div>
              )}

              <button
                type="button"
                className={styles.payBtn}
                onClick={handlePayNow}
                disabled={submitting}
              >
                {submitting ? (
                  <><div className={styles.spinnerSmall} /> Processing…</>
                ) : (
                  `Pay ${fmt(displayAmount)} →`
                )}
              </button>

              <button
                type="button"
                className={styles.backBtn}
                onClick={() => { setErrorMsg(""); setStep(STEP.DETAILS); }}
              >
                ← Back
              </button>
            </div>
          )}

          {/* ── STEP 2b: CRYPTO ADDRESS (after checkout created) ── */}
          {step === STEP.PAYMENT && checkoutResponse && paymentMethod === "crypto" && (
            <div className={styles.card}>
              <h2 className={styles.cardTitle}>Send crypto</h2>
              <CryptoPayment
                checkoutData={{
                  ...checkoutResponse,
                  // Backend returns these from merchant settlement config
                  destination_wallet: checkoutResponse.destination_wallet,
                  amount_usd: checkoutResponse.amount_usd,
                  currency_code: checkoutResponse.currency_code || "USDT",
                  blockchain_code: checkoutResponse.blockchain_code || "TRX",
                }}
                onCopied={() => {}}
              />
            </div>
          )}

          {/* ── CARD MODAL ── */}
          {showCardModal && checkoutResponse && (
            <div className={styles.modalOverlay}>
              <div className={styles.modalContainer}>
                <CardPaymentModal
                  payramUrl={checkoutResponse.payram_payment_url}
                  onSuccess={handleTestSuccess}
                  onCancel={() => {
                    setShowCardModal(false);
                    clearInterval(pollRef.current);
                    setCheckoutResponse(null);
                    setSubmitting(false);
                    setErrorMsg("");
                  }}
                  isTestMode={isTestMode}
                />
              </div>
            </div>
          )}

          {/* ── STEP 3: CONFIRMING ── */}
          {step === STEP.CONFIRMING && <ConfirmingScreen />}

          {/* ── STEP 4: SUCCESS ── */}
          {step === STEP.SUCCESS && product && (
            <SuccessScreen
              product={product}
              merchant={merchant}
              checkoutId={checkoutResponse?.checkout_id}
              redirectUrl={product.success_redirect_url}
            />
          )}
        </div>
      </div>

      {/* Footer — "Powered by CashSpace", NOT PayRam */}
      <footer className={styles.footer}>
        <span className={styles.poweredBy}>
          Powered by <strong>CashSpace</strong>
        </span>
        <span className={styles.footerSep}>·</span>
        <a href="/privacy" className={styles.footerLink}>Privacy</a>
        <span className={styles.footerSep}>·</span>
        <a href="/terms" className={styles.footerLink}>Terms</a>
      </footer>
    </div>
  );
}