// src/components/ui/ConfirmModal.jsx
import React, { useState, createContext, useContext } from 'react';
import styles from './ConfirmModal.module.css';

const ConfirmContext = createContext();

export function ConfirmModalProvider({ children }) {
  const [config, setConfig] = useState({ isOpen: false, title: '', message: '', onConfirm: null });

  const confirm = (title, message, onConfirm) => {
    setConfig({ isOpen: true, title, message, onConfirm });
  };

  const handleConfirm = () => {
    config.onConfirm?.();
    setConfig({ isOpen: false, title: '', message: '', onConfirm: null });
  };

  const handleCancel = () => {
    setConfig({ isOpen: false, title: '', message: '', onConfirm: null });
  };

  return (
    <ConfirmContext.Provider value={{ confirm }}>
      {children}
      {config.isOpen && (
        <div className={styles.overlay} onClick={handleCancel}>
          <div className={styles.modal} onClick={e => e.stopPropagation()}>
            <div className={styles.header}>
              <h3>{config.title}</h3>
              <button className={styles.close} onClick={handleCancel}>×</button>
            </div>
            <div className={styles.body}>{config.message}</div>
            <div className={styles.footer}>
              <button className={styles.cancel} onClick={handleCancel}>Cancel</button>
              <button className={styles.ok} onClick={handleConfirm}>OK</button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  return useContext(ConfirmContext);
}