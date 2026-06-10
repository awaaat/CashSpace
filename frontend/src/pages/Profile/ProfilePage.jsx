import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../../store/authStore";
import { authApi } from "../../api/auth";
import styles from "./ProfilePage.module.css";

export default function ProfilePage() {
  const navigate = useNavigate();
  const { user, setUser } = useAuthStore();
  const [profile, setProfile] = useState({
    first_name: "",
    last_name: "",
    phone_number: "",
  });
  const [password, setPassword] = useState({
    current_password: "",
    new_password: "",
    new_password_confirm: "",
  });
  const [loading, setLoading] = useState({ profile: false, password: false });
  const [message, setMessage] = useState({ profile: "", password: "" });
  const [error, setError] = useState({ profile: "", password: "" });

  useEffect(() => {
    if (user) {
      setProfile({
        first_name: user.first_name || "",
        last_name: user.last_name || "",
        phone_number: user.phone_number || "",
      });
    }
  }, [user]);

  const handleProfileSubmit = async (e) => {
    e.preventDefault();
    setLoading((prev) => ({ ...prev, profile: true }));
    setError((prev) => ({ ...prev, profile: "" }));
    try {
      const { data } = await authApi.updateProfile(profile);
      setUser(data);
      setMessage((prev) => ({ ...prev, profile: "Profile updated successfully" }));
      setTimeout(() => setMessage((prev) => ({ ...prev, profile: "" })), 3000);
    } catch (err) {
      setError((prev) => ({ ...prev, profile: "Failed to update profile" }));
    } finally {
      setLoading((prev) => ({ ...prev, profile: false }));
    }
  };

  const handlePasswordSubmit = async (e) => {
    e.preventDefault();
    if (password.new_password !== password.new_password_confirm) {
      setError((prev) => ({ ...prev, password: "New passwords do not match" }));
      return;
    }
    setLoading((prev) => ({ ...prev, password: true }));
    setError((prev) => ({ ...prev, password: "" }));
    try {
      await authApi.changePassword({
        current_password: password.current_password,
        new_password: password.new_password,
      });
      setMessage((prev) => ({ ...prev, password: "Password changed. Please log in again." }));
      setPassword({ current_password: "", new_password: "", new_password_confirm: "" });
      setTimeout(() => setMessage((prev) => ({ ...prev, password: "" })), 3000);
    } catch (err) {
      setError((prev) => ({ ...prev, password: err.response?.data?.current_password?.[0] || "Failed to change password" }));
    } finally {
      setLoading((prev) => ({ ...prev, password: false }));
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <button className={styles.backButton} onClick={() => navigate("/dashboard")}>
          ← Back to Dashboard
        </button>
        <h1 className={styles.title}>Profile Settings</h1>
      </div>

      <div className={styles.grid}>
        {/* Personal Information */}
        <div className={styles.card}>
          <h2 className={styles.cardTitle}>Personal Information</h2>
          <form onSubmit={handleProfileSubmit} className={styles.form}>
            <div className={styles.field}>
              <label className={styles.label}>First name</label>
              <input
                className={styles.input}
                value={profile.first_name}
                onChange={(e) => setProfile({ ...profile, first_name: e.target.value })}
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label}>Last name</label>
              <input
                className={styles.input}
                value={profile.last_name}
                onChange={(e) => setProfile({ ...profile, last_name: e.target.value })}
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label}>Phone number</label>
              <input
                className={styles.input}
                value={profile.phone_number}
                onChange={(e) => setProfile({ ...profile, phone_number: e.target.value })}
                placeholder="+254..."
              />
            </div>
            {message.profile && <div className={styles.success}>{message.profile}</div>}
            {error.profile && <div className={styles.error}>{error.profile}</div>}
            <button type="submit" className={styles.button} disabled={loading.profile}>
              {loading.profile ? <span className={styles.spinner} /> : "Save changes"}
            </button>
          </form>
        </div>

        {/* Security */}
        <div className={styles.card}>
          <h2 className={styles.cardTitle}>Security</h2>
          <form onSubmit={handlePasswordSubmit} className={styles.form}>
            <div className={styles.field}>
              <label className={styles.label}>Current password</label>
              <input
                type="password"
                className={styles.input}
                value={password.current_password}
                onChange={(e) => setPassword({ ...password, current_password: e.target.value })}
                required
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label}>New password</label>
              <input
                type="password"
                className={styles.input}
                value={password.new_password}
                onChange={(e) => setPassword({ ...password, new_password: e.target.value })}
                required
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label}>Confirm new password</label>
              <input
                type="password"
                className={styles.input}
                value={password.new_password_confirm}
                onChange={(e) => setPassword({ ...password, new_password_confirm: e.target.value })}
                required
              />
            </div>
            {message.password && <div className={styles.success}>{message.password}</div>}
            {error.password && <div className={styles.error}>{error.password}</div>}
            <button type="submit" className={styles.button} disabled={loading.password}>
              {loading.password ? <span className={styles.spinner} /> : "Change password"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}