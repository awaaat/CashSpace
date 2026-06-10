import React from "react";
import { Navbar } from "./Navbar";
import { Sidebar } from "./Sidebar";
import styles from "./Layout.module.css";

export const Layout = ({ children }) => {
  return (
    <div className={styles.layout}>
      <Navbar />
      <div className={styles.container}>
        <Sidebar />
        <main className={styles.main}>{children}</main>
      </div>
    </div>
  );
};