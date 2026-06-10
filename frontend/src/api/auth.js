// src/api/auth.js
import api from "./axios";

const getAuthHeader = () => {
  const token = localStorage.getItem("access_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
};

export const authApi = {
  register: (data) => api.post("/auth/register/", data),
  login: (data) => api.post("/auth/login/", data),
  logout: (refresh) => api.post("/auth/logout/", { refresh }),
  me: () => api.get("/auth/me/"),
  updateProfile: (data) => api.patch("/auth/me/", data),
  changePassword: (data) => api.post("/auth/change-password/", data),
  forgotPassword: (email) => api.post("/auth/forgot-password/", { email }),
  resetPassword: (data) => api.post("/auth/reset-password/", data),
  verifyEmail: (token) => api.get(`/auth/verify-email/?token=${token}`),

  // ── Token refresh — was missing, caused crash in useAuth silent refresh ──
  refreshToken: (data) => api.post("/auth/token/refresh/", data),

  // ── Wallet management ──
  getCryptoWallets: () => api.get("/auth/wallets/", { headers: getAuthHeader() }),

  addCryptoWallet: (data) => {
    console.log("Adding wallet:", data);
    return api.post("/auth/wallets/", data, { headers: getAuthHeader() });
  },

  updateCryptoWallet: (id, data) =>
    api.patch(`/auth/wallets/${id}/`, data, { headers: getAuthHeader() }),

  setDefaultWallet: (id) =>
    api.post(`/auth/wallets/${id}/set-default/`, {}, { headers: getAuthHeader() }),

  deleteCryptoWallet: (id) => {
    console.log("Deleting wallet ID:", id);
    return api.delete(`/auth/wallets/${id}/`, { headers: getAuthHeader() });
  },

  // Admin
  adminUsers: (params) => api.get("/auth/admin/users/", { params }),
  adminUser: (id) => api.get(`/auth/admin/users/${id}/`),
  adminSuspend: (id) => api.post(`/auth/admin/users/${id}/suspend/`),
  adminActivate: (id) => api.post(`/auth/admin/users/${id}/activate/`),
  auditLogs: (params) => api.get("/auth/admin/audit-logs/", { params }),

  // Notifications
  getNotifications: (params) => api.get("/notifications/", { params }),
  markNotificationRead: (id) => api.post(`/notifications/${id}/mark_read/`),
  markAllNotificationsRead: () => api.post("/notifications/mark_all_read/"),
  getUnreadNotificationCount: () => api.get("/notifications/unread_count/"),
};