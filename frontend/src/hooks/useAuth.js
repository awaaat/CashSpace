// src/hooks/useAuth.js
// Enterprise-grade authentication hook with token refresh, silent refresh, and proper dependency management.
// Fixed: prevents double initialization in React 18 strict mode.

import { useEffect, useCallback, useRef } from "react";
import { useAuthStore } from "../store/authStore";
import { authApi } from "../api/auth";

// Helper: decode JWT and extract expiration timestamp (seconds since epoch)
const getTokenExpiry = (token) => {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return payload.exp * 1000; // convert to milliseconds
  } catch {
    return null;
  }
};

export function useAuth() {
  const { user, isAuthenticated, isLoading, setUser, clearUser, setLoading } = useAuthStore();

  // --- Token refresh logic ---
  const refreshAccessToken = useCallback(async () => {
    const refresh = localStorage.getItem("refresh_token");
    if (!refresh) return false;
    try {
      const { data } = await authApi.refreshToken({ refresh });
      localStorage.setItem("access_token", data.access);
      return true;
    } catch (error) {
      clearUser();
      return false;
    }
  }, [clearUser]);

  // --- Silent refresh loop ---
  useEffect(() => {
    const scheduleRefresh = () => {
      const accessToken = localStorage.getItem("access_token");
      if (!accessToken) return null;

      const expiryMs = getTokenExpiry(accessToken);
      if (!expiryMs) return null;

      const now = Date.now();
      const timeToExpiry = expiryMs - now;
      // Refresh 2 minutes before expiry or immediately if already expired
      const refreshIn = Math.max(0, timeToExpiry - 2 * 60 * 1000);

      return setTimeout(async () => {
        const success = await refreshAccessToken();
        if (success) {
          // Schedule next refresh after new token is acquired
          scheduleRefresh();
        } else {
          clearUser();
        }
      }, refreshIn);
    };

    let timeoutId = scheduleRefresh();
    return () => {
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [refreshAccessToken, clearUser]);

  // --- Initial auth check (runs once on mount) ---
  const initialCheckDone = useRef(false);

  useEffect(() => {
    if (initialCheckDone.current) return;
    initialCheckDone.current = true;

    const token = localStorage.getItem("access_token");
    if (!token) {
      setLoading(false);
      return;
    }

    // Validate token and fetch user
    authApi.me()
      .then(({ data }) => setUser(data))
      .catch(() => clearUser())
      .finally(() => setLoading(false));
  }, [setUser, clearUser, setLoading]);

  // --- Public methods ---
  const login = async (email, password) => {
    const { data } = await authApi.login({ email, password });
    localStorage.setItem("access_token", data.access);
    localStorage.setItem("refresh_token", data.refresh);
    setUser(data.user);
    return data;
  };

  const logout = async () => {
    const refresh = localStorage.getItem("refresh_token");
    if (refresh) {
      try {
        await authApi.logout(refresh);
      } catch (err) {
        // Ignore logout errors
      }
    }
    clearUser();
  };

  const register = async (payload) => {
    const { data } = await authApi.register(payload);
    return data;
  };

  // Expose manual refresh if needed
  const refreshToken = async () => {
    return await refreshAccessToken();
  };

  return {
    user,
    isAuthenticated,
    isLoading,
    login,
    logout,
    register,
    refreshToken,
  };
}