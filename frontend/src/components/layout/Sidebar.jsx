import React from "react";
import { NavLink } from "react-router-dom";
import { useAuthStore } from "../../store/authStore";
import styles from "./Sidebar.module.css";

const navItems = [
  { to: "/dashboard", label: "Overview", icon: "⬡" },
  { to: "/payment", label: "Payments", icon: "◈" },
  { to: "/profile", label: "Profile", icon: "◎" },
  { to: "/settings", label: "Settings", icon: "⚙" },
];

const adminItems = [
  { to: "/admin/users", label: "Users", icon: "◪" },
  { to: "/admin/payments", label: "All Payments", icon: "◧" },
  { to: "/admin/logs", label: "Audit Logs", icon: "◩" },
];

export const Sidebar = () => {
  const { user } = useAuthStore();
  const isAdmin = user?.role === "admin";

  return (
    <aside className={styles.sidebar}>
      <div className={styles.userSection}>
        <div className={styles.avatar}>
          {(user?.first_name?.[0] || user?.email?.[0] || "U").toUpperCase()}
        </div>
        <div className={styles.userDetails}>
          <span className={styles.userName}>{user?.first_name || user?.email}</span>
          <span className={styles.userRole}>{user?.role || "user"}</span>
        </div>
      </div>

      <nav className={styles.nav}>
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `${styles.navLink} ${isActive ? styles.active : ""}`
            }
          >
            <span className={styles.icon}>{item.icon}</span>
            <span>{item.label}</span>
          </NavLink>
        ))}
        {isAdmin && (
          <>
            <div className={styles.divider} />
            {adminItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `${styles.navLink} ${isActive ? styles.active : ""}`
                }
              >
                <span className={styles.icon}>{item.icon}</span>
                <span>{item.label}</span>
              </NavLink>
            ))}
          </>
        )}
      </nav>
    </aside>
  );
};