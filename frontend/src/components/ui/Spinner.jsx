import React from "react";
import styles from "./Spinner.module.css";

export const Spinner = ({ size = "md", color = "gold", className = "" }) => {
  return (
    <div
      className={`${styles.spinner} ${styles[`size-${size}`]} ${styles[`color-${color}`]} ${className}`}
      aria-label="Loading"
    />
  );
};