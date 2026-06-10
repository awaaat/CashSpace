// src/store/authStore.js
// Enterprise-grade auth store with persistence, rehydration, and token management.

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

export const useAuthStore = create(
  persist(
    (set, get) => ({
      user: null,
      isAuthenticated: false,
      isLoading: true,

      setUser: (user) => set({ user, isAuthenticated: !!user, isLoading: false }),
      
      clearUser: () => {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        set({ user: null, isAuthenticated: false, isLoading: false });
      },
      
      setLoading: (isLoading) => set({ isLoading }),

      // Helper to update user profile fields (name, phone, etc.)
      updateUserProfile: (profileData) => {
        const user = get().user;
        if (user) {
          set({ user: { ...user, ...profileData } });
        }
      },

      // Helper to update BTC wallet (legacy, kept for compatibility)
      updateUserWallet: (walletAddress, walletLabel) => {
        const user = get().user;
        if (user) {
          set({
            user: {
              ...user,
              btc_wallet_address: walletAddress,
              btc_wallet_label: walletLabel,
            },
          });
        }
      },
    }),
    {
      name: "cashspace-auth", // localStorage key
      storage: createJSONStorage(() => localStorage),
      // Only persist user and auth status; isLoading is transient
      partialize: (state) => ({
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
      onRehydrateStorage: () => (state) => {
        if (state) {
          // After rehydration, ensure loading flag is false
          state.setLoading(false);
        }
      },
    }
  )
);