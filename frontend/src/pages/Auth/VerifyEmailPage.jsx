import React, { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { authApi } from "../../api/auth";               // was ../api/auth
import { Button } from "../../components/ui/Button";    // was ../components/ui/Button
import styles from "./AuthPage.module.css";

export default function VerifyEmailPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState("verifying"); // verifying, success, error
  const token = searchParams.get("token");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      return;
    }
    authApi.verifyEmail(token)
      .then(() => setStatus("success"))
      .catch(() => setStatus("error"));
  }, [token]);

  return (
    <div className={styles.root}>
      <div className={styles.right} style={{ gridColumn: "1/-1" }}>
        <div className={styles.card}>
          {status === "verifying" && <div className={styles.spinner} />}
          {status === "success" && (
            <>
              <div className={styles.successIcon}>✓</div>
              <h2>Email verified!</h2>
              <p>You can now log in to your account.</p>
              <Button onClick={() => navigate("/login")}>Go to login →</Button>
            </>
          )}
          {status === "error" && (
            <>
              <div className={styles.errorBanner}>Invalid or expired verification link.</div>
              <Button onClick={() => navigate("/")}>Back home</Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}