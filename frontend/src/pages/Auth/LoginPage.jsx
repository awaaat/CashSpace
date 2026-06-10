import React, { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import styles from "./AuthPage.module.css";

export default function LoginPage() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [searchParams] = useSearchParams();
  const registered = searchParams.get("registered");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
      navigate("/dashboard");
    } catch (err) {
      setError(err.response?.data?.detail || "Invalid credentials");
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

        <p className={styles.tagline}>The fastest fiat-to-Crypto gateway</p>

        <div className={styles.stats}>
          <div className={styles.stat}><strong>48K+</strong><span>Transactions</span></div>
          <div className={styles.stat}><strong>~2min</strong><span>Settlement</span></div>
          <div className={styles.stat}><strong>Non-custodial</strong></div>
        </div>

        <form onSubmit={handleSubmit} className={styles.form}>
          {registered && (
            <div style={{background:"rgba(34,197,94,0.1)",border:"1px solid rgba(34,197,94,0.2)",borderRadius:"12px",padding:"10px",fontSize:"13px",color:"#86efac",textAlign:"center"}}>
              ✓ Account created! Check your email to verify, then sign in.
            </div>
          )}
          {error && <div className={styles.errorMessage}>{error}</div>}

          <div className={styles.field}>
            <label>Email</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" required autoFocus />
          </div>

          <div className={styles.field}>
            <label>Password</label>
            <div className={styles.passwordWrapper}>
              <input type={showPassword ? "text" : "password"} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" required />
              <button type="button" className={styles.showBtn} onClick={() => setShowPassword(!showPassword)}>
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>
          </div>

          <div className={styles.forgotLink}>
            <Link to="/forgot-password">Forgot password?</Link>
          </div>

          <button type="submit" className={styles.submitBtn} disabled={loading}>
            {loading ? "Signing in..." : "Sign in →"}
          </button>
        </form>

        <p className={styles.switchLink}>
          Don't have an account? <Link to="/register">Create one →</Link>
        </p>
      </div>
    </div>
  );
}
