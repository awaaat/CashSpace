import React, { forwardRef, useState } from "react";
import styles from "./Input.module.css";

export const Input = forwardRef(
  (
    {
      label,
      error,
      type = "text",
      icon,
      iconPosition = "left",
      showPasswordToggle = false,
      fullWidth = true,
      className = "",
      ...props
    },
    ref
  ) => {
    const [showPassword, setShowPassword] = useState(false);
    const inputType = showPasswordToggle ? (showPassword ? "text" : "password") : type;

    return (
      <div className={`${styles.field} ${fullWidth ? styles.fullWidth : ""} ${className}`}>
        {label && <label className={styles.label}>{label}</label>}
        <div className={styles.inputWrapper}>
          {icon && iconPosition === "left" && <span className={styles.leftIcon}>{icon}</span>}
          <input
            ref={ref}
            type={inputType}
            className={`${styles.input} ${error ? styles.error : ""} ${icon ? styles.hasIcon : ""}`}
            {...props}
          />
          {showPasswordToggle && (
            <button
              type="button"
              className={styles.passwordToggle}
              onClick={() => setShowPassword(!showPassword)}
              tabIndex={-1}
            >
              {showPassword ? "Hide" : "Show"}
            </button>
          )}
          {icon && iconPosition === "right" && <span className={styles.rightIcon}>{icon}</span>}
        </div>
        {error && <span className={styles.errorMsg}>{error}</span>}
      </div>
    );
  }
);