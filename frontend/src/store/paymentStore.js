// src/store/paymentStore.js
// Enterprise-grade payment store with pagination, filtering, caching, and pagination state.

import { create } from "zustand";
import { devtools } from "zustand/middleware";

export const usePaymentStore = create(
  devtools(
    (set, get) => ({
      // State
      payments: [],
      total: 0,
      page: 1,
      pageSize: 10,
      filters: {
        status: null,
        blockchain_code: null,
        currency_code: null,
        payout_status: null,
        date_from: null,
        date_to: null,
      },
      isLoading: false,
      error: null,

      // Actions
      setPayments: (payments, total) => set({ payments, total }),
      setLoading: (isLoading) => set({ isLoading }),
      addPayment: (payment) =>
        set((state) => ({ payments: [payment, ...state.payments] })),
      
      updatePayment: (paymentId, updates) =>
        set((state) => ({
          payments: state.payments.map((p) =>
            p.id === paymentId ? { ...p, ...updates } : p
          ),
        })),
      
      setPage: (page) => set({ page }),
      setPageSize: (pageSize) => set({ pageSize, page: 1 }),
      setFilters: (newFilters) =>
        set((state) => ({
          filters: { ...state.filters, ...newFilters },
          page: 1, // reset to first page when filters change
        })),
      clearFilters: () =>
        set({
          filters: {
            status: null,
            blockchain_code: null,
            currency_code: null,
            payout_status: null,
            date_from: null,
            date_to: null,
          },
          page: 1,
        }),
      setError: (error) => set({ error }),
      clearError: () => set({ error: null }),
      
      // Reset entire store (e.g., on logout)
      reset: () =>
        set({
          payments: [],
          total: 0,
          page: 1,
          pageSize: 10,
          filters: {
            status: null,
            blockchain_code: null,
            currency_code: null,
            payout_status: null,
            date_from: null,
            date_to: null,
          },
          isLoading: false,
          error: null,
        }),
    }),
    { name: "payment-store" }
  )
);