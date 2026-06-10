// src/pages/Auth/ForgotPasswordPage.jsx
// Enterprise-grade forgot password page with proper CSS class handling.

import React, { useState } from "react";
import { Link } from "react-router-dom";
import { authApi } from "../../api/auth";
import styles from "./AuthPage.module.css";

/**
 * ForgotPasswordPage Component
 * Allows user to request a password reset email.
 */
export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await authApi.forgotPassword(email);
      setSubmitted(true);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to send reset email. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.authContainer}>
      {/* Background decorative elements (safe fallback) */}
      <div className={styles.backgroundNoise} />
      <div className={styles.backgroundOrb1} />
      <div className={styles.backgroundOrb2} />

      {/* Left panel – branding */}
      <div className={styles.authLeft}>
        <div className={styles.authLeftContent}>
          <Link to="/" className={styles.logoLink}>
            <span className={styles.logoMark}>C</span>
            <span className={styles.logoText}>CashSpace</span>
          </Link>
          <div className={styles.authQuote}>
            <p>We'll send you a password reset link to your email address.</p>
          </div>
        </div>
      </div>

      {/* Right panel – form */}
      <div className={styles.authRight}>
        <div className={styles.authCard}>
          <div className={styles.authCardHeader}>
            <h1 className={styles.authTitle}>Reset password</h1>
            <p className={styles.authSubtitle}>Enter your account email</p>
          </div>

          {submitted ? (
            <div className={styles.successState}>
              <div className={styles.successIcon}>✓</div>
              <p className={styles.successMessage}>
                If an account exists with that email, we've sent a password reset link.
              </p>
              <Link to="/login" className={styles.backLink}>
                ← Back to sign in
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className={styles.authForm}>
              <div className={styles.formGroup}>
                <label htmlFor="email" className={styles.formLabel}>Email address</label>
                <input
                  id="email"
                  type="email"
                  className={styles.formInput}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  required
                  disabled={loading}
                />
              </div>
              {error && <div className={styles.errorBanner}>{error}</div>}
              <button
                type="submit"
                className={styles.authButton}
                disabled={loading}
              >
                {loading ? <span className={styles.spinner} /> : "Send reset link →"}
              </button>
            </form>
          )}

          {!submitted && (
            <p className={styles.switchLink}>
              <Link to="/login">← Back to sign in</Link>
            </p>
          )}
        </div>
      </div>
    </div>
  );
}