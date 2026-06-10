import React, { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuthStore } from "../../store/authStore";
import { useAuth } from "../../hooks/useAuth";
import styles from "./Navbar.module.css";

export const Navbar = () => {
  const { user } = useAuthStore();
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [scrolled, setScrolled] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <nav className={`${styles.navbar} ${scrolled ? styles.scrolled : ""}`}>
      <div className={styles.container}>
        <Link to="/" className={styles.logo}>
          <span className={styles.logoMark}>C</span>
          <span className={styles.logoText}>CashSpace</span>
        </Link>

        <div className={`${styles.navLinks} ${mobileMenuOpen ? styles.open : ""}`}>
          <Link to="/dashboard" className={styles.navLink}>
            Dashboard
          </Link>
          <Link to="/payment" className={styles.navLink}>
            Payments
          </Link>
          <Link to="/profile" className={styles.navLink}>
            Profile
          </Link>
          {user?.role === "admin" && (
            <Link to="/admin" className={styles.navLink}>
              Admin
            </Link>
          )}
          <button onClick={handleLogout} className={styles.logoutBtn}>
            Sign out
          </button>
        </div>

        <div className={styles.userInfo}>
          <span className={styles.userName}>{user?.first_name || user?.email}</span>
          <button
            className={styles.mobileToggle}
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            aria-label="Menu"
          >
            ☰
          </button>
        </div>
      </div>
    </nav>
  );
};