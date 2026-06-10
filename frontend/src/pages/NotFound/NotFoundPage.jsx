import React from "react";
import { Link } from "react-router-dom";
import { Button } from "../../components/ui/Button";    // was ../components/ui/Button
import styles from "./NotFoundPage.module.css";

export default function NotFoundPage() {
  return (
    <div className={styles.container}>
      <div className={styles.content}>
        <h1 className={styles.code}>404</h1>
        <h2 className={styles.title}>Page not found</h2>
        <p className={styles.description}>
          The page you're looking for doesn't exist or has been moved.
        </p>
        <Link to="/">
          <Button variant="primary">Go back home →</Button>
        </Link>
      </div>
    </div>
  );
}