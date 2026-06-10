// frontend/src/api/creator.js
import api from "./axios";

export const creatorApi = {
  // Public (no authentication)
  getPublicAsset: (slug) => api.get(`/creator/pay/${slug}/`),
  checkout: (slug, data) => api.post(`/creator/pay/${slug}/checkout/`, data),

  // Profile
  getProfile: () => api.get("/creator/profile/"),
  updateProfile: (data) => api.patch("/creator/profile/", data),

  // Assets
  getAssets: () => api.get("/creator/assets/"),
  getAsset: (id) => api.get(`/creator/assets/${id}/`),
  createAsset: (data) => api.post("/creator/assets/", data),
  updateAsset: (id, data) => api.patch(`/creator/assets/${id}/`, data),
  deleteAsset: (id) => api.delete(`/creator/assets/${id}/`),
  getAssetStats: (id) => api.get(`/creator/assets/${id}/stats/`),

  // Affiliate program for an asset
  getAffiliateProgram: (assetId) => api.get(`/creator/assets/${assetId}/affiliate/`),
  updateAffiliateProgram: (assetId, data) => api.patch(`/creator/assets/${assetId}/affiliate/`, data),

  // Discount codes
  getDiscountCodes: (assetId) => api.get(`/creator/assets/${assetId}/discounts/`),
  createDiscountCode: (assetId, data) => api.post(`/creator/assets/${assetId}/discounts/`, data),
  updateDiscountCode: (assetId, discountId, data) => api.patch(`/creator/assets/${assetId}/discounts/${discountId}/`, data),
  deleteDiscountCode: (assetId, discountId) => api.delete(`/creator/assets/${assetId}/discounts/${discountId}/`),

  // Sales
  getSales: (params) => api.get("/creator/sales/", { params }),
  getSale: (id) => api.get(`/creator/sales/${id}/`),

  // Global stats
  getStats: () => api.get("/creator/stats/"),
};