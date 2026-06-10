import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import styles from "./AuthPage.module.css";

export default function RegisterPage() {
  const navigate = useNavigate();
  const { register } = useAuth();
  const [step, setStep] = useState(1);
  const [form, setForm] = useState({
    email: "",
    first_name: "",
    last_name: "",
    password: "",
    password_confirm: "",
  });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const handleNext = (e) => {
    e.preventDefault();
    if (!form.email || !form.first_name) {
      setError("Please fill all fields");
      return;
    }
    setError("");
    setStep(2);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (form.password !== form.password_confirm) {
      setError("Passwords do not match");
      return;
    }
    setError("");
    setLoading(true);
    try {
      await register(form);
      navigate("/login?registered=true");
    } catch (err) {
      const data = err.response?.data;
      setError(data?.email?.[0] || data?.password?.[0] || data?.detail || "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <Link to="/" className={styles.logo}>
          <span className={styles.logoMark}>C</span>
          <span className={styles.logoText}>CashSpace</span>
        </Link>

        <p className={styles.tagline}>
          The fastest fiat-to-Crypto gateway
        </p>

        <div className={styles.stats}>
          <div className={styles.stat}>
            <strong>48K+</strong>
            <span>Transactions</span>
          </div>
          <div className={styles.stat}>
            <strong>~2min</strong>
            <span>Settlement</span>
          </div>
          <div className={styles.stat}>
            <strong>Non-custodial</strong>
          </div>
        </div>

        <form onSubmit={step === 1 ? handleNext : handleSubmit} className={styles.form}>
          {error && <div className={styles.errorMessage}>{error}</div>}

          {step === 1 && (
            <>
              <div className={styles.field}>
                <label>First name</label>
                <input
                  value={form.first_name}
                  onChange={(e) => setForm({ ...form, first_name: e.target.value })}
                  placeholder="Allan"
                  required
                />
              </div>
              <div className={styles.field}>
                <label>Last name</label>
                <input
                  value={form.last_name}
                  onChange={(e) => setForm({ ...form, last_name: e.target.value })}
                  placeholder="Smith"
                />
              </div>
              <div className={styles.field}>
                <label>Email</label>
                <input
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  placeholder="you@example.com"
                  required
                />
              </div>
            </>
          )}

          {step === 2 && (
            <>
              <div className={styles.field}>
                <label>Password</label>
                <div className={styles.passwordWrapper}>
                  <input
                    type={showPassword ? "text" : "password"}
                    value={form.password}
                    onChange={(e) => setForm({ ...form, password: e.target.value })}
                    placeholder="Min. 8 characters"
                    required
                  />
                </div>
              </div>
              <div className={styles.field}>
                <label>Confirm password</label>
                <div className={styles.passwordWrapper}>
                  <input
                    type="password"
                    value={form.password_confirm}
                    onChange={(e) => setForm({ ...form, password_confirm: e.target.value })}
                    placeholder="Repeat password"
                    required
                  />
                  <button
                    type="button"
                    className={styles.showBtn}
                    onClick={() => setShowPassword(!showPassword)}
                  >
                    {showPassword ? "Hide" : "Show"}
                  </button>
                </div>
              </div>
            </>
          )}

          <div className={styles.buttonGroup}>
            {step === 2 && (
              <button type="button" className={styles.backBtn} onClick={() => setStep(1)}>
                ← Back
              </button>
            )}
            <button type="submit" className={styles.submitBtn} disabled={loading}>
              {loading ? "Creating..." : step === 1 ? "Continue →" : "Create account →"}
            </button>
          </div>
        </form>

        <p className={styles.switchLink}>
          Already have an account? <Link to="/login">Sign in →</Link>
        </p>
      </div>
    </div>
  );
}