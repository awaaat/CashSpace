import React from "react";
import styles from "./Button.module.css";

/**
 * Enterprise-grade Button component with variants, sizes, loading state, and full accessibility.
 * @param {string} variant - "primary", "secondary", "outline", "ghost", "danger"
 * @param {string} size - "sm", "md", "lg"
 * @param {boolean} isLoading - shows spinner and disables
 * @param {boolean} isFullWidth - takes full width of parent
 * @param {function} onClick - click handler
 * @param {string} type - "button", "submit", "reset"
 * @param {React.ReactNode} children
 * @param {string} className - additional classes
 * @param {boolean} disabled
 */
export const Button = ({
  variant = "primary",
  size = "md",
  isLoading = false,
  isFullWidth = false,
  onClick,
  type = "button",
  children,
  className = "",
  disabled = false,
  ...rest
}) => {
  const classes = [
    styles.btn,
    styles[`btn-${variant}`],
    styles[`btn-${size}`],
    isFullWidth && styles.fullWidth,
    isLoading && styles.loading,
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button
      type={type}
      className={classes}
      onClick={onClick}
      disabled={disabled || isLoading}
      aria-busy={isLoading}
      {...rest}
    >
      {isLoading && <span className={styles.spinner} />}
      <span className={styles.content}>{children}</span>
    </button>
  );
};