// src/pages/Auth/ResetPasswordPage.jsx
// Enterprise-grade reset password page.

import React, { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { authApi } from "../../api/auth";
import styles from "./AuthPage.module.css";

export default function ResetPasswordPage() {
  const { token } = useParams();
  const navigate = useNavigate();
  const [form, setForm] = useState({ new_password: "", confirm_password: "" });
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (form.new_password !== form.confirm_password) {
      setError("Passwords do not match");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await authApi.resetPassword({ token, new_password: form.new_password });
      setSuccess(true);
      setTimeout(() => navigate("/login"), 3000);
    } catch (err) {
      setError(err.response?.data?.detail || "Reset failed. Token may be expired or invalid.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.root}>
      <div className={styles.noise} />
      <div className={styles.orb1} /><div className={styles.orb2} />
      <div className={styles.right} style={{ gridColumn: "1/-1" }}>
        <div className={styles.card}>
          <div className={styles.cardHead}>
            <h1 className={styles.cardTitle}>Set new password</h1>
            <p className={styles.cardSub}>Choose a strong, unique password</p>
          </div>
          {success ? (
            <div className={styles.successIcon}>✓</div>
          ) : (
            <form onSubmit={handleSubmit} className={styles.form}>
              <div className={styles.field}>
                <label className={styles.label}>New password</label>
                <input
                  type="password"
                  className={styles.input}
                  value={form.new_password}
                  onChange={(e) => setForm({ ...form, new_password: e.target.value })}
                  required
                />
              </div>
              <div className={styles.field}>
                <label className={styles.label}>Confirm password</label>
                <input
                  type="password"
                  className={styles.input}
                  value={form.confirm_password}
                  onChange={(e) => setForm({ ...form, confirm_password: e.target.value })}
                  required
                />
              </div>
              {error && <div className={styles.errorBanner}>{error}</div>}
              <button type="submit" className={styles.button} disabled={loading}>
                {loading ? <span className={styles.spinner} /> : "Reset password →"}
              </button>
            </form>
          )}
          {!success && (
            <p className={styles.switchLink}>
              <a href="/login">← Back to sign in</a>
            </p>
          )}
        </div>
      </div>
    </div>
  );
}