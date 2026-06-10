// frontend/src/hooks/usePayment.js
import { useState, useCallback, useRef } from "react";
import { paymentsApi } from "../api/payments";
import { usePaymentStore } from "../store/paymentStore";

export function usePayments() {
  const { payments, total, isLoading, setPayments, setLoading, addPayment } =
    usePaymentStore();
  const [error, setError] = useState(null);

  // Use refs for the store setters so fetchPayments deps array stays stable.
  // Zustand setters are already stable, but wrapping in refs makes the
  // ESLint exhaustive-deps rule happy and prevents any accidental re-creation.
  const setPaymentsRef = useRef(setPayments);
  const setLoadingRef = useRef(setLoading);
  setPaymentsRef.current = setPayments;
  setLoadingRef.current = setLoading;

  const fetchPayments = useCallback(async (params = {}) => {
    setLoadingRef.current(true);
    setError(null);
    try {
      const { data } = await paymentsApi.list(params);
      setPaymentsRef.current(data.results || data, data.count || 0);
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to load payments");
    } finally {
      setLoadingRef.current(false);
    }
  }, []); // stable — no deps needed thanks to refs

  const initiatePayment = useCallback(
    async (amount_usd, walletId) => {
      const { data } = await paymentsApi.initiate(amount_usd, walletId);
      addPayment(data);
      return data;
    },
    [addPayment]
  );

  const pollStatus = useCallback(async (id) => {
    const { data } = await paymentsApi.status(id);
    return data;
  }, []);

  return {
    payments,
    total,
    isLoading,
    error,
    fetchPayments,
    initiatePayment,
    pollStatus,
  };
}