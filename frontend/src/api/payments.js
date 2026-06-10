// frontend/src/api/payments.js
import api from "./axios";

export const paymentsApi = {
  initiate: (amount_usd, wallet_id) => api.post("/payments/initiate/", { amount_usd, wallet_id }),
  list: (params) => api.get("/payments/", { params }),
  detail: (id) => api.get(`/payments/${id}/`),
  status: (id) => api.get(`/payments/${id}/status/`),
  adminList: (params) => api.get("/payments/admin/", { params }),
};