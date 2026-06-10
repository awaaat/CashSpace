// frontend/src/api/merchant.js
import api from "./axios";

export const merchantApi = {
  // ── Public checkout (no auth) ───────────────────────────────────────────────
  getMerchantLanding: (merchantSlug) =>
    api.get(`/pay/${merchantSlug}/`),
  getProductCheckoutPage: (merchantSlug, productSlug) =>
    api.get(`/pay/${merchantSlug}/${productSlug}/`),
  submitCheckout: (merchantSlug, productSlug, data, testMode = false) =>
    api.post(`/pay/${merchantSlug}/${productSlug}/checkout/${testMode ? "?mode=test" : ""}`, data),
  getCheckoutStatus: (merchantSlug, productSlug, checkoutId) =>
    api.get(`/pay/${merchantSlug}/${productSlug}/checkout/${checkoutId}/status/`),
  testCompleteCheckout: (merchantSlug, productSlug, checkoutId) =>
    api.post(`/pay/${merchantSlug}/${productSlug}/checkout/${checkoutId}/test-complete/`),

  // ── Merchant registration & profile ────────────────────────────────────────
  register: (data) => api.post("/merchants/register/", data),
  getMe: () => api.get("/merchants/me/"),
  updateMe: (data) => api.patch("/merchants/me/", data),

  // ── Analytics ───────────────────────────────────────────────────────────────
  getAnalytics: (period = "30d") =>
    api.get("/merchants/me/analytics/", { params: { period } }),

  // ── API Keys ────────────────────────────────────────────────────────────────
  getKeys: () =>
    api.get("/merchants/me/keys/"),
  rotateKey: (env) =>
    api.post("/merchants/me/keys/rotate/", { env }),         // env: "test" | "live"
  toggleMode: (mode) =>
    api.post("/merchants/me/keys/toggle-mode/", { mode }),   // mode: "test" | "live"

  // ── Sales CRM ───────────────────────────────────────────────────────────────
  getSales: (params) => api.get("/merchants/me/sales/", { params }),
  getSale: (id) => api.get(`/merchants/me/sales/${id}/`),
  retriggerAutomation: (saleId) =>
    api.post(`/merchants/me/sales/${saleId}/retrigger/`),

  // ── Products ────────────────────────────────────────────────────────────────
  getProducts: () => api.get("/merchants/me/products/"),
  getProduct: (id) => api.get(`/merchants/me/products/${id}/`),
  createProduct: (data) => api.post("/merchants/me/products/", data),
  updateProduct: (id, data) => api.patch(`/merchants/me/products/${id}/`, data),
  deleteProduct: (id) => api.delete(`/merchants/me/products/${id}/`),
  testSale: (productId) =>
    api.post(`/merchants/me/products/${productId}/test-sale/`),

  // ── Post-payment actions ────────────────────────────────────────────────────
  getActions: (productId) =>
    api.get(`/merchants/me/products/${productId}/actions/`),
  createAction: (productId, data) =>
    api.post(`/merchants/me/products/${productId}/actions/`, data),
  updateAction: (productId, actionId, data) =>
    api.patch(`/merchants/me/products/${productId}/actions/${actionId}/`, data),
  deleteAction: (productId, actionId) =>
    api.delete(`/merchants/me/products/${productId}/actions/${actionId}/`),

  // ── Webhook logs ────────────────────────────────────────────────────────────
  getWebhookLogs: (params) =>
    api.get("/merchants/me/webhook-logs/", { params }),
  retryWebhook: (logId) =>
    api.post(`/merchants/me/webhook-logs/${logId}/retry/`),

  // ── Admin (staff only) ──────────────────────────────────────────────────────
  adminListMerchants: (params) =>
    api.get("/merchants/admin/", { params }),
  adminGetMerchant: (id) =>
    api.get(`/merchants/admin/${id}/`),
  adminUpdateMerchant: (id, data) =>
    api.patch(`/merchants/admin/${id}/`, data),
  adminAllSales: (params) =>
    api.get("/merchants/admin/sales/", { params }),
};