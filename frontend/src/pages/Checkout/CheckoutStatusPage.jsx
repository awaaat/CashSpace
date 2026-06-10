import React, { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { merchantApi } from "../../api/merchant";
import styles from "./CheckoutStatusPage.module.css";

const POLL_INTERVAL = 3000; // 3 seconds
const MAX_POLLS = 40;       // 2 minutes total

export default function CheckoutStatusPage() {
  const { merchantSlug, productSlug, checkoutId } = useParams();
  const navigate = useNavigate();

  const [status, setStatus] = useState(null);
  const [polls, setPolls] = useState(0);
  const [error, setError] = useState("");
  const isTest = new URLSearchParams(window.location.search).get("mode") === "test";

  const poll = useCallback(async () => {
    try {
      const { data } = await merchantApi.getCheckoutStatus(merchantSlug, productSlug, checkoutId);
      setStatus(data);

      if (data.payment_status === "FILLED" || data.status === "completed") {
        // Success — redirect if merchant set a redirect URL
        if (data.success_redirect_url) {
          setTimeout(() => { window.location.href = data.success_redirect_url; }, 2500);
        }
        return true; // stop polling
      }

      if (["CANCELLED", "FAILED"].includes(data.payment_status)) {
        return true; // stop polling
      }

      return false;
    } catch {
      setError("Could not reach the server. Retrying…");
      return false;
    }
  }, [merchantSlug, productSlug, checkoutId]);

  useEffect(() => {
    let cancelled = false;
    let timer;

    const run = async () => {
      if (cancelled) return;
      const done = await poll();
      setPolls(p => p + 1);
      if (!done && polls < MAX_POLLS) {
        timer = setTimeout(run, POLL_INTERVAL);
      }
    };

    run();
    return () => { cancelled = true; clearTimeout(timer); };
  }, []);  // eslint-disable-line

  const paymentStatus = status?.payment_status;
  const checkoutStatus = status?.status;

  const isSuccess = paymentStatus === "FILLED" || checkoutStatus === "completed";
  const isFailed  = ["CANCELLED", "FAILED"].includes(paymentStatus);
  const isPending = !isSuccess && !isFailed;

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        {/* Logo */}
        <div className={styles.logo}>
          <div className={styles.logoMark}>C</div>
          <span className={styles.logoText}>CashSpace</span>
        </div>

        {/* Icon */}
        <div className={`${styles.iconWrap} ${isSuccess ? styles.iconSuccess : isFailed ? styles.iconFailed : styles.iconPending}`}>
          {isSuccess && <span className={styles.icon}>✓</span>}
          {isFailed  && <span className={styles.icon}>✕</span>}
          {isPending && <span className={styles.spinner} />}
        </div>

        {/* Heading */}
        {isPending && (
          <>
            <h1 className={styles.title}>Confirming your payment…</h1>
            <p className={styles.sub}>
              {isTest
                ? "Test mode — this page will auto-confirm shortly."
                : "This usually takes under a minute. Don't close this tab."}
            </p>
          </>
        )}
        {isSuccess && (
          <>
            <h1 className={styles.titleSuccess}>Payment confirmed!</h1>
            <p className={styles.sub}>
              {status?.automation_triggered
                ? "Your access has been delivered. Check your email."
                : "Your payment is confirmed. Access delivery is in progress."}
            </p>
          </>
        )}
        {isFailed && (
          <>
            <h1 className={styles.titleFailed}>Payment {paymentStatus?.toLowerCase()}</h1>
            <p className={styles.sub}>Your payment was not completed. No charge was made.</p>
          </>
        )}

        {/* Status rows */}
        {status && (
          <div className={styles.statusRows}>
            <div className={styles.statusRow}>
              <span className={styles.statusLabel}>Payment</span>
              <span className={`${styles.statusVal} ${isSuccess ? styles.green : isFailed ? styles.red : styles.muted}`}>
                {paymentStatus || "Pending"}
              </span>
            </div>
            <div className={styles.statusRow}>
              <span className={styles.statusLabel}>Automation</span>
              <span className={`${styles.statusVal} ${status.automation_triggered ? styles.green : styles.muted}`}>
                {status.automation_triggered ? "Delivered" : "Pending"}
              </span>
            </div>
            {isTest && (
              <div className={styles.statusRow}>
                <span className={styles.statusLabel}>Mode</span>
                <span className={`${styles.statusVal} ${styles.testBadge}`}>TEST</span>
              </div>
            )}
          </div>
        )}

        {error && <div className={styles.error}>{error}</div>}

        {/* Actions */}
        <div className={styles.actions}>
          {isFailed && (
            <button
              className={styles.retryBtn}
              onClick={() => navigate(`/pay/${merchantSlug}/${productSlug}/`)}
            >
              Try again
            </button>
          )}
          {isSuccess && status?.success_redirect_url && (
            <a href={status.success_redirect_url} className={styles.redirectBtn}>
              Continue →
            </a>
          )}
        </div>

        <div className={styles.footer}>
          Secured by <strong>CashSpace</strong>
        </div>
      </div>
    </div>
  );
}